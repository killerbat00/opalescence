#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""
import hashlib
import io
import logging
import os
from typing import Union, Dict, List, Optional

import bitstring as bitstring

from .messages import Request, Block, Piece
from opalescence.btlib.metainfo import MetaInfoFile

logger = logging.getLogger(__name__)


class FileWriter:
    """
    Writes piece data to temp memory for now.
    Will eventually flush data to the disk.
    """
    writing_pieces = []

    def __init__(self, torrent: MetaInfoFile):
        self.filename = os.path.join(os.path.abspath(os.path.dirname(__file__)), torrent.name)
        self.fd = open(self.filename, "wb")
        self.piece_length = torrent.piece_length
        self.buffer = io.BytesIO()

    def write(self, piece: Piece):
        """
        Writes the piece's data to the buffer
        """
        if piece in self.writing_pieces:
            return
        else:
            self.writing_pieces.append(Piece)
        offset = piece.index * self.piece_length
        data = piece.data.getvalue()
        try:
            logger.debug(f"Writing piece: {piece}")
            self.fd.seek(offset, 0)
            self.fd.write(data)
            self.fd.flush()
            del self.writing_pieces[self.writing_pieces.index(Piece)]
        except OSError as oe:
            del self.writing_pieces[self.writing_pieces.index(Piece)]
            logger.debug(f"Encountered OSError when writing {piece.index}")
            raise oe


class Requester:
    """
    Responsible for requesting and downloading pieces from peers.
    A single requester is shared between all peers to which the local peer is connected.

    We currently use a naive sequential strategy.
    """

    def __init__(self, torrent: MetaInfoFile):
        self.torrent = torrent
        self.piece_length = torrent.piece_length
        self.last_piece_length = torrent.last_piece_length
        self.piece_peer_map: Dict(int, set) = {i: set() for i in range(len(self.torrent.pieces))}
        self.downloaded_pieces: Dict(int, Piece) = {}
        self.downloading_pieces: Dict(int, Union(Piece, None)) = {i: None for i in range(len(self.torrent.pieces))}
        self.pending_requests: List(Request) = []

    @property
    def complete(self):
        return len(self.downloaded_pieces) == len(self.torrent.pieces)

    def add_available_piece(self, peer_id: str, index: int) -> None:
        """
        Sent when a peer has a piece of the torrent.

        :param peer_id: The peer that has the piece
        :param index: The index of the piece
        """
        self.piece_peer_map[index].add(peer_id)

    def add_peer_bitfield(self, peer_id: str, bitfield: bitstring.BitArray) -> None:
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer_id:  The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        for i, b in enumerate(bitfield):
            if b:
                self.piece_peer_map[i].add(peer_id)

    def remove_peer(self, peer_id: str) -> None:
        """
        Removes a peer from this requester's data structures in the case
        that our communication with that peer has stopped

        :param peer_id: peer to remove
        """
        for _, peer_set in self.piece_peer_map.items():
            peer_set.discard(peer_id)

    def received_block(self, block: Block) -> Union[None, Piece]:
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
        if not piece:
            logger.debug(f"Disregarding. I already have {block}")
            return
        piece.add_block(block)

        if not piece.complete:
            return

        piece.data.seek(0)
        piece_data = piece.data.read()
        piece_hash = hashlib.sha1(piece_data).digest()
        if piece_hash != self.torrent.pieces[piece.index]:
            logger.debug(
                f"Hash for received piece {piece.index} doesn't match\n"
                f"Received: {piece_hash}\n"
                f"Expected: {self.torrent.pieces[piece.index]}")
            piece.reset()
        else:
            logger.debug(f"Completed piece received: {piece}")
            self.downloaded_pieces[piece.index] = piece
            self.downloading_pieces[piece.index] = None
            return piece

    def _next_piece_index_for_peer(self, peer_id: str, start: int = -1) -> \
            Optional[int]:
        """
        Finds the next piece index that the peer has available that we can
        request.

        Works like this:
        1. Check the incomplete pieces we are downloading to see if peer has one
        2. If there are no incomplete pieces the peer can give us, request
           the next piece it can give us.
        3. Look through the available pieces to find one the peer has
        4. If none available, the peer is useless to us.
        :param peer_id: peer requesting a piece
        :param start: index to start at when searching through currently
                      downloading and available pieces
        :return: piece's index or None if not available
        """
        # Find the next piece index in the pieces we are downloading that the
        # peer said it could send us
        for i, v in self.downloading_pieces.items():
            if v:
                if i > start:
                    if peer_id in self.piece_peer_map[i]:
                        return i

        # We couldn't find an incomplete piece index. This means the peer
        # can't give us any pieces that we are currently downloading. So,
        # we start requesting the next piece that hasn't been complete.
        for i, peer_set in self.piece_peer_map.items():
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
        :return: A downloading piece, adding it to the list
        """
        piece = self.downloading_pieces[piece_index]
        if not piece:
            if piece_index == len(self.torrent.pieces) - 1:
                piece = Piece(piece_index, self.last_piece_length)
            else:
                piece = Piece(piece_index, self.piece_length)
            self.downloading_pieces[piece_index] = piece
        return piece

    def next_request(self, peer_id: str) -> Optional[Request]:
        """
        Requests the next block we need. The current strategy is a naive
        strategy that requests pieces and blocks sequentially from remote peers.
        We only request pieces from a peer if that peer has told
        us it has those pieces.

        :param peer_id: The remote peer who's asking for a new request's id
        :return: A new request, or None if that isn't possible.
        """

        # Find the next piece index for which the peer has an available piece
        piece_index = self._next_piece_index_for_peer(peer_id)
        if piece_index is None:
            return

        # After we've found the next index the peer has,
        # check to see we've already started downloading it.
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

        if piece.index == len(self.torrent.pieces) - 1:
            request = Request(piece.index, next_block_begin, length=self.last_piece_length)
        else:
            request = Request(piece.index, next_block_begin, peer_id=peer_id)

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

            if piece.index == len(self.torrent.pieces) - 1:
                request = Request(piece.index, next_block_begin, length=self.last_piece_length)
            else:
                request = Request(piece.index, next_block_begin, peer_id=peer_id)

        self.pending_requests.append(request)
        return request
