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

        # dictionary of peers and indices of the pieces the peer has available
        self.peer_piece_map: dict[PeerInfo, set[int]] = defaultdict(set)

        # canonical list of unfulfilled requests
        self._unfulfilled_requests: list[Request] = []
        self._peer_unfulfilled_requests: dict[PeerInfo, set[Request]] = defaultdict(set)

    def _build_requests(self) -> list[Request]:
        """
        Builds the list of unfulfilled requests.
        When we need to fill a queue with requests, we just make copies of
        requests in our list and mark the ones we have with the peer we send
        the request to.

        :return: a list of all the requests needed to download the torrent
        """
        requests = []

        for piece in self.torrent.pieces:
            for block in piece.blocks:
                request = Request.from_block(block)
                if request:
                    requests.append(request)

        return requests

    def add_available_piece(self, peer: PeerInfo, index: int):
        """
        Called when a peer advertises it has a piece available.

        :param peer: The peer that has the piece
        :param index: The index of the piece
        """
        if not self._unfulfilled_requests:
            self._unfulfilled_requests = self._build_requests()
        self.peer_piece_map[peer].add(index)

    def add_peer_bitfield(self, peer: PeerInfo, bitfield: bitstring.BitArray):
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer:  The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        if not self._unfulfilled_requests:
            self._unfulfilled_requests = self._build_requests()

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
            for request in self._peer_unfulfilled_requests[peer]:
                request.peer_id = ""
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

        if request in self._peer_unfulfilled_requests[peer]:
            self._peer_unfulfilled_requests[peer].discard(request)
            found = True

            try:
                self._unfulfilled_requests.remove(request)
            except ValueError:
                pass

        return found

    def remove_requests_for_piece(self, piece_index: int):
        """
        Removes all pending requests with the given piece index.
        Called when a completed piece has been received.

        :param piece_index: piece index whose requests should be removed
        """
        to_discard = []
        for i, request in enumerate(self._unfulfilled_requests):
            if request.index == piece_index:
                to_discard.append(request)
                for request_set in self._peer_unfulfilled_requests.values():
                    request_set.discard(request)
        for r in to_discard:
            self._unfulfilled_requests.remove(r)

    def remove_peer(self, peer: PeerInfo):
        """
        Removes a peer from this requester's data structures in the case
        that our communication with that peer has stopped

        :param peer: peer to remove
        """
        if peer in self.peer_piece_map:
            del self.peer_piece_map[peer]

        self.remove_requests_for_peer(peer)

    def fill_peer_request_queue(self, peer: PeerInfo, msg_queue: asyncio.Queue) -> bool:
        """
        Fills the given queue with up to 10 new requests for the peer, returning
        True if more requests were added or False otherwise.

        :param peer: The peer asking for a top up
        :param msg_queue: the message queue to place the requests into
        :return: True if more requests were added or the peer has any outstanding.
        """
        added_more = False
        num_needed = 10 - len(self._peer_unfulfilled_requests[peer])

        for _ in range(num_needed):
            request = self.next_request_for_peer(peer)
            if not request:  # no more requests for this peer
                break
            msg_queue.put_nowait(request)
            added_more = True
        return added_more

    def next_request_for_peer(self, peer: PeerInfo) -> Optional[Request]:
        """
        Finds the next request for the peer.

        Searches over each unfulfilled request (currently in order), skipping
        those that have been requested from other peers or the peer doesn't have
        available until finding a request. The peer is marked as being the requester
        and a copy of the request is returned.

        :param peer: The peer to retrieve the next request for.
        :return: The next `Request` to send, or None if not available.
        """
        if peer not in self.peer_piece_map:
            return
        if len(self.peer_piece_map[peer]) == 0:
            return

        found_request = None
        for request in self._unfulfilled_requests:
            if request.peer_id:
                continue
            if request.index not in self.peer_piece_map[peer]:
                continue
            request.peer_id = peer.peer_id
            self._peer_unfulfilled_requests[peer].add(request)
            found_request = request
            break

        return found_request
