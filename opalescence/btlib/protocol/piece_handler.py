#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""
import hashlib
import io
import logging
import os
from typing import Union, Dict, List

import bitstring as bitstring

from .messages import Request, Block, Piece
from .peer import Peer
from ..torrent import Torrent

logger = logging.getLogger(__name__)


class Writer:
    """
    Writes piece data to temp memory for now.
    Will eventually flush data to the disk.
    """

    def __init__(self, torrent: Torrent):
        self.filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), torrent.name)
        self.piece_length = torrent.piece_length
        self.buffer = io.BytesIO()

    def write(self, piece: Piece):
        """
        Writes the piece's data to the buffer
        """
        offset = piece.index * self.piece_length
        piece.data.seek(0)
        data = piece.data.read()
        try:
            with open(self.filename, "ab+") as f:
                f.seek(offset, 0)
                f.write(data)
                f.flush()
        except OSError as oe:
            logger.debug(f"Encountered OSError when writing {piece.index}")
            raise oe


class Requester:
    """
    Responsible for requesting and downloading pieces from peers.
    A single requester is shared between all peers to which the local peer is connected.

    We currently use a naive sequential strategy.
    """

    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.piece_length = torrent.piece_length
        self.piece_writer = Writer(torrent)
        self.available_pieces: Dict(int, set) = {i: set() for i in range(len(self.torrent.pieces))}
        self.downloaded_pieces: Dict(int, Piece) = {}
        self.downloading_pieces: Dict(int, Union(Piece, None)) = {i: None for i in range(len(self.torrent.pieces))}
        self.pending_requests: List(Request) = []

    def add_available_piece(self, peer: Peer, index: int) -> None:
        """
        Sent when a peer has a piece of the torrent.

        :param peer:  The peer has the piece
        :param index: The index of the piece
        """
        self.available_pieces[index].add(str(peer))

    def add_peer_bitfield(self, peer: Peer, bitfield: bitstring.BitArray) -> None:
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer:     The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        for i, b in enumerate(bitfield):
            if b:
                self.available_pieces[i].add(str(peer))

    def remove_peer(self, peer: Peer) -> None:
        """
        Removes a peer from this requester's data structures in the case
        that our communication with that peer has stopped

        :param peer: peer to remove
        """
        for _, peer_set in self.available_pieces.items():
            peer_set.discard(str(peer))

    def received_block(self, block: Block) -> None:
        """
        Called when we've received a block from the remote peer.
        First, see if there are other blocks from that piece already downloaded.
        If so, add this block to the piece and pend a request for the remaining blocks
        that we would need.

        :param block: The piece message with the data and e'erthang
        """
        # Remove the pending request for this block if there is one
        r = Request(block.index, block.begin)
        if r in self.pending_requests:
            index = self.pending_requests.index(r)
            del self.pending_requests[index]

        piece = self.downloading_pieces.get(block.index)
        piece.add_block(block)

        if not piece.complete:
            return

        piece.data.seek(0)
        piece_data = piece.data.read()
        piece_hash = hashlib.sha1(piece_data).digest()
        if piece_hash != self.torrent.pieces[piece.index]:
            logger.debug(
                f"Hash for received piece {piece.index} doesn't match expected hash\n"
                f"Received: {piece_hash}\n"
                f"Expected: {self.torrent.pieces[piece.index]}")
            piece.reset()
        else:
            self.downloaded_pieces[piece.index] = piece
            self.downloading_pieces[piece.index] = None
            self.piece_writer.write(piece)

    def _next_piece_index_for_peer(self, peer_id: str, start: int = -1) -> Union[int, None]:
        """
        Finds the next piece index that the peer has available that we can request.
        Works like this:
        1. Check the incomplete pieces we are downloading to see if a peer has any one of those.
        2. If there are not any incomplete pieces, the peer can give us, request the next piece it can give us.
        3. Look through the available pieces to find one that is not complete and that the peer has
        4. If none available, the peer is useless to us.
        :param peer_id: peer requesting a piece
        :param start: index to start at when searching through currently downloading and available pieces
        :return: piece's index or None if not available
        """
        # Find the next piece index in the pieces we are currently downloading that the
        # peer said it could send us
        for k, v in self.downloading_pieces.items():
            if v:
                if k > start:
                    if peer_id in self.available_pieces[k]:
                        return k

        # We couldn't find an incomplete piece index. This means the peer can't give us any pieces that
        # we are currently downloading. So, we start requesting the next piece that hasn't been complete.
        for i, peer_set in self.available_pieces.items():
            if i > start:
                if i not in self.downloaded_pieces:
                    if peer_id in peer_set:
                        return i

        # There are no pieces the peer can send us :(
        logger.debug(f"{peer_id}: Has no pieces available to send.")
        return

    def _try_get_downloading_piece(self, piece_index: int) -> Piece:
        """
        :param piece_index: index for the piece
        :return: A downloading piece, adding it to the list if it wasn't already there
        """
        piece = self.downloading_pieces[piece_index]
        if not piece:
            piece = Piece(piece_index, self.piece_length)
            self.downloading_pieces[piece_index] = piece
        return piece

    def next_request(self, peer_id: str) -> Union[Request, None]:
        """
        Requests the next block we need. The current strategy is a naive strategy that requests pieces and blocks
        sequentially from remote peers.
        We only request pieces from a peer if that peer has told us it has those pieces.

        :param peer_id: The remote peer who's asking for a new request's id
        :return: A new request, or None if that isn't possible.
        """
        # Find the next piece index for which the peer has an available piece
        piece_index = self._next_piece_index_for_peer(peer_id)
        if piece_index is None:
            return

        # After we've found the next index the peer has, check to see we've already started downloading it.
        piece = self._try_get_downloading_piece(piece_index)

        # Find where the next request for a block should begin
        next_block_begin = piece.next_block()
        while next_block_begin is None:
            # There are no more blocks to request for this piece, try to find another piece
            piece_index = self._next_piece_index_for_peer(peer_id, start=piece_index)
            if piece_index is None:
                return
            piece = self._try_get_downloading_piece(piece_index)
            next_block_begin = piece.next_block()

        request = Request(piece.index, next_block_begin)
        piece_index = piece.index
        while request in self.pending_requests:
            next_block_begin = piece.next_block()
            while next_block_begin is None:
                # There are no more blocks to request for this piece, try to find another piece
                piece_index = self._next_piece_index_for_peer(peer_id, start=piece_index)
                if piece_index is None:
                    return
                piece = self._try_get_downloading_piece(piece_index)
                next_block_begin = piece.next_block()
            request = Request(piece.index, next_block_begin)

        self.pending_requests.append(request)
        return request