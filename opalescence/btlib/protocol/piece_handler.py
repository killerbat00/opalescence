# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""

__all__ = ['PieceRequester']

import asyncio
import dataclasses
import logging
from collections import defaultdict
from typing import Optional

import bitstring

from .messages import Request, Block
from .metainfo import MetaInfoFile
from .peer_info import PeerInfo

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class WriteBuffer:
    buffer = b''
    offset = 0


class PieceRequester:
    """
    Responsible for requesting pieces from peers.
    A single requester is shared between all peers to which
    the local peer is connected.

    We currently use a naive sequential requesting strategy.
    """
    _block_size = 2 ** 14

    def __init__(self, torrent: MetaInfoFile):
        self.torrent = torrent
        # peer identification
        self.piece_peer_map: dict[int, set[PeerInfo]] = \
            {i: set() for i in range(self.torrent.num_pieces)}
        self.peer_piece_map: dict[PeerInfo, set[int]] = defaultdict(set)

        # canonical list of unfulfilled requests
        self._unfulfilled_requests: list[Request] = self._build_requests()
        self._peer_unfulfilled_requests: dict[PeerInfo, set[int]] = defaultdict(set)

    def _build_requests(self) -> list[Request]:
        """
        Builds the list of unfulfilled requests.
        When we need to fill a queue with requests, we just make copies of
        requests in our list and mark the ones we have with the peer we send
        the request to.

        :return: a list of all the requests needed to download the torrent
        """
        requests = []
        block_size = min(self._block_size, self.torrent.piece_length)
        for i, piece in enumerate(self.torrent.pieces):
            if piece.complete:
                continue
            piece_offset = 0
            while (size := min(block_size, piece.length - piece_offset)) > 0:
                requests.append(Request(i, piece_offset, size))
                piece_offset += size

        return requests

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

    def peer_is_interesting(self, peer: PeerInfo) -> bool:
        """
        Returns whether or not the peer is interesting to us.
        We currently check if the peer has at least num_pieces // 2 pieces
        that we don't have, unless we only need num_pieces // 4 pieces in
        which case the peer is interesting if it has at least 1.

        :param peer: The peer we're curious about.
        :return: True if the peer is interesting, False otherwise
        """
        if peer not in self.peer_piece_map:
            return False

        needed = set([i for i, piece in enumerate(self.torrent.pieces)
                      if not piece.complete])
        peer_has = set([i for i in self.peer_piece_map[peer] if i in needed])

        # if not needed or not peer_has:
        #    return False

        # if len(needed) <= self.torrent.num_pieces // 4:
        #    return True
        # return len(peer_has) >= self.torrent.num_pieces // 2

        return len(peer_has) > 0

    def remove_requests_for_peer(self, peer: PeerInfo):
        """
        Removes all pending requests for a peer.
        Called when the peer disconnects or chokes us.

        :param peer: peer whose pending requests we should remove
        """
        if peer in self._peer_unfulfilled_requests:
            for request_index in self._peer_unfulfilled_requests[peer]:
                self._unfulfilled_requests[request_index].peer_id = ""

            del self._peer_unfulfilled_requests[peer]

    def remove_requests_for_block(self, peer: PeerInfo, block: Block) -> bool:
        """
        Removes all pending requests for the given block.

        :param peer: `PeerInfo` of the peer who sent the block.
        :param block: `Block` to remove from pending requests.
        :return: True if removed, False otherwise
        """
        if peer not in self._peer_unfulfilled_requests:
            return False
        if len(self._peer_unfulfilled_requests[peer]) == 0:
            return False

        found = False
        request = Request(block.index, block.begin, len(block.data))
        request_index = None
        for request_index in self._peer_unfulfilled_requests[peer]:
            found_rqst = self._unfulfilled_requests[request_index]
            if found_rqst == request and found_rqst.peer_id == peer.peer_id:
                found = True
                break

        if found and request_index:
            del self._unfulfilled_requests[request_index]
            self._peer_unfulfilled_requests[peer].discard(request_index)
        return found

    def remove_requests_for_piece(self, piece_index: int):
        """
        Removes all pending requests with the given piece index.
        Called when a completed piece has been received.

        :param piece_index: piece index whose requests should be removed
        """
        for i, request in enumerate(self._unfulfilled_requests):
            if request.index == piece_index:
                del self._unfulfilled_requests[i]
                for request_sets in self._peer_unfulfilled_requests.values():
                    request_sets.discard(i)

    def remove_peer(self, peer: PeerInfo):
        """
        Removes a peer from this requester's data structures in the case
        that our communication with that peer has stopped

        :param peer: peer to remove
        """
        for peer_set in self.piece_peer_map.values():
            if peer in peer_set:
                peer_set.discard(peer)

        if peer in self.peer_piece_map:
            del self.peer_piece_map[peer]

        self.remove_requests_for_peer(peer)

    def fill_peer_request_queue(self, peer: PeerInfo, msg_queue: asyncio.Queue):
        num_needed = 10 - msg_queue.qsize()
        pass

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
        if len(self.pending_requests) >= 25:
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
            if request in self.pending_requests:
                # TODO: move on to the next request/block
                return

            self.pending_requests.append(request)
            return request
