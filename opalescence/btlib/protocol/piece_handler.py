# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""

__all__ = ['PieceRequester']

import dataclasses
import logging
from collections import defaultdict
from typing import Dict, List, Set, Optional

import bitstring

from .messages import Request, Piece, Block
# TODO: stop importing from a parent package.
from .peer_info import PeerInfo
from ..metainfo import MetaInfoFile, FileWriter

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class WriteBuffer:
    buffer = b''
    offset = 0


class PieceRequester:
    """
    Responsible for requesting and downloading pieces from peers.
    A single requester is shared between all peers to which the local peer is connected.

    We currently use a naive sequential strategy.
    """

    def __init__(self, torrent: MetaInfoFile):
        self.torrent = torrent
        self.piece_peer_map: Dict[int, Set[PeerInfo]] = {i: set() for i in range(self.torrent.num_pieces)}
        self.peer_piece_map: Dict[PeerInfo, Set[int]] = defaultdict(set)
        self.pending_requests: List[Request] = []
        self.writer = FileWriter(torrent)

    def add_available_piece(self, peer: PeerInfo, index: int):
        """
        Called when a peer advertises it has a piece available.

        :param peer: The peer that has the piece
        :param index: The index of the piece
        """
        self.piece_peer_map[index].add(peer)
        self.peer_piece_map[peer].add(index)

    def add_peer_bitfield(self, peer: PeerInfo, bitfield: bitstring.BitArray):
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer:  The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        for i, b in enumerate(bitfield):
            if b:
                self.add_available_piece(peer, i)

    def remove_pending_requests_for_peer(self, peer: PeerInfo):
        """
        Removes all pending requests for a peer.
        Called when the peer disconnects or chokes us.

        :param peer: peer whose pending requests ew should remove
        """
        for i, request in enumerate(self.pending_requests):
            if request.peer_id == peer.peer_id:
                del self.pending_requests[i]

    def remove_request(self, request: Request) -> bool:
        """
        Removes all pending requests that match the given request.

        :param request: `Request` to remove from pending requests.
        :return: True if removed, False otherwise
        """
        removed = False
        for i, pending_rqst in enumerate(self.pending_requests):
            if pending_rqst == request:
                del self.pending_requests[i]
                removed = True
        return removed

    def remove_requests_for_piece(self, piece_index: int):
        """
        Removes all pending requests with the given piece index.

        :param piece_index: piece index whose requests should be removed
        """
        for i, request in enumerate(self.pending_requests):
            if request.index == piece_index:
                del self.pending_requests[i]

    def remove_peer(self, peer: PeerInfo):
        """
        Removes a peer from this requester's data structures in the case
        that our communication with that peer has stopped

        :param peer: peer to remove
        """
        for _, peer_set in self.piece_peer_map.items():
            if peer in peer_set:
                peer_set.discard(peer)

        if peer in self.peer_piece_map:
            del self.peer_piece_map[peer]

        self.remove_pending_requests_for_peer(peer)

    async def received_block(self, peer: PeerInfo, block: Block):
        """
        Called when we've received a block from the remote peer.
        First, see if there are other blocks from that piece already downloaded.
        If so, add this block to the piece and pend a request for the remaining blocks
        that we would need.

        :param peer: The peer who sent the block
        :param block: The piece message with the data and e'erthang
        """
        logger.info(f"{peer} sent {block}")
        self.peer_piece_map[peer].add(block.index)
        self.piece_peer_map[block.index].add(peer)

        if block.index > len(self.torrent.pieces):
            logger.debug(f"Disregarding. Piece {block.index} does not exist.")

        piece = self.torrent.pieces[block.index]
        if piece.complete:
            logger.debug(f"Disregarding. I already have {block}")
            return

        # Remove the pending requests for this block if there are any
        r = Request(block.index, block.begin, min(piece.remaining, Request.size))
        if not self.remove_request(r):
            logger.debug(f"Disregarding. I did not request {block}")
            return

        piece.add_block(block)
        if piece.complete:
            await self.piece_complete(piece)

    async def piece_complete(self, piece: Piece):
        """
        Called when the last block of a piece has been received.
        Validates the piece hash matches, writes the data, and marks the piece complete.
        :param piece: the completed piece.
        """
        h = piece.hash()
        if h != self.torrent.piece_hashes[piece.index]:
            logger.error(
                f"Hash for received piece {piece.index} doesn't match\n"
                f"Received: {h}\n"
                f"Expected: {self.torrent.piece_hashes[piece.index]}")
            piece.reset()
        else:
            logger.info(f"Completed piece received: {piece}")
            self.remove_requests_for_piece(piece.index)
            await self.writer.write(piece)
            piece.mark_complete()

    def next_request_for_peer(self, peer: PeerInfo) -> Optional[Request]:
        """
        Finds the next request that we can send to the peer.

        Works like this:
        1. Check each piece the peer has to find the first incomplete piece.
        2. Request the next block for the first incomplete piece found.
        3. If we already have a request for an incomplete piece's next block, return.
        4. If none available, the peer is useless to us.

        TODO: Multiple per-block pending requests.

        :param peer: peer requesting a piece
        :return: piece's index or None if not available
        """
        if self.torrent.complete:
            logger.info("Already complete.")
            return

        if len(self.pending_requests) >= 50:
            logger.error(f"Too many currently pending requests.")
            return

        # Find the next piece index in the pieces we are downloading that the
        # peer said it could send us
        for i in self.peer_piece_map[peer]:
            piece = self.torrent.pieces[i]
            if piece.complete:
                continue

            size = min(piece.remaining, Request.size)
            request = Request(i, piece.next_block, size, peer.peer_id)
            while request in self.pending_requests:
                logger.info(f"{peer}: We have an outstanding request for {request}")
                # TODO: move on to the next request/block
                return

            logger.info(f"{peer}: Successfully got request {request}.")
            self.pending_requests.append(request)
            return request

        # There are no pieces the peer can send us :(
        logger.info(f"{peer}: Has no pieces available to send.")
        return
