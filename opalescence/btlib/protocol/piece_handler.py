#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""
import hashlib
import io
import logging
import os

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
    A single requester is shared between all peers to which we are connected.
    """

    def __init__(self, torrent):
        self.torrent = torrent
        self.total_pieces = len(torrent.pieces)
        self.piece_length = torrent.piece_length
        self.pc_writer = Writer(torrent)
        self.bitfield = None
        self.available_pieces = {i: set() for i in range(self.total_pieces)}
        self.pending_requests = []
        self.downloaded_pieces = {}
        self.broken_pieces = []

    def peer_has_piece(self, peer: Peer, pc_index: int) -> None:
        """
        Sent when a protocol has a piece of the torrent.

        :param peer:     The protocol who has the piece
        :param pc_index: the index of the piece
        """
        self.available_pieces[pc_index].add(peer)

    def peer_sent_bitfield(self, peer: Peer, bitfield: bitstring.BitArray) -> None:
        """
        Updates our dictionary of pieces with data from the remote protocol

        :param peer:     The protocol who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the protocol
        """
        if not self.bitfield:
            self.bitfield = bitstring.BitArray(length=len(bitfield))

        for i, b in enumerate(bitfield):
            if b:
                self.available_pieces[i].add(peer)

    def remove_peer(self, peer: Peer) -> None:
        """
        Removes a protocol from this requester's data structures in the case that our communication
        with that protocol has stopped

        :param peer: protocol to remove
        """
        for _, peer_set in self.available_pieces.items():
            peer_set.discard(peer)

    def peer_sent_block(self, block: Block) -> None:
        """
        Called when we've received a block from the remote protocol.
        First, see if there are other blocks from that piece already downloaded.
        If so, add this block to the piece and pend a request for the remaining blocks
        that we would need.

        :param block: The piece message with the data and e'erthang
        """
        r = Request(block.index, block.begin)
        if r in self.pending_requests:
            index = self.pending_requests.index(r)
            del self.pending_requests[index]

        pc = self.downloaded_pieces.get(block.index)

        pc.add_block(block)
        if pc.complete:
            pc.data.seek(0)
            pc_data = pc.data.read()
            pc_hash = hashlib.sha1(pc_data).digest()
            if pc_hash != self.torrent.pieces[pc.index]:
                logger.debug(f"Received piece doesn't match expected hash {pc.index}")
                self.broken_pieces.append(pc)
            else:
                self.bitfield[pc.index] = 1
                self.pc_writer.write(pc)

    def next_request(self) -> Request:
        """
        Requests the next block we need. The current strategy is a naive strategy that requests pieces and blocks
        sequentially from remote peers.
        """
        if not self.downloaded_pieces:
            piece = Piece(0, self.torrent.piece_length)
            self.downloaded_pieces[piece.index] = piece
            request = Request(piece.index, piece.next_block())
            self.pending_requests.append(request)
            return request

        current_piece = self.downloaded_pieces.get(len(self.downloaded_pieces) - 1)
        next_block_begin = current_piece.next_block()

        if next_block_begin is None:
            # Start requesting the next piece
            piece = Piece(current_piece.index + 1, self.torrent.piece_length)
            self.downloaded_pieces[piece.index] = piece
            request = Request(piece.index, piece.next_block())
            self.pending_requests.append(request)
            return request

        request = Request(current_piece.index, next_block_begin)
        while request in self.pending_requests:
            next_offset = current_piece.next_block()
            if next_offset is None:
                # Start requesting the next piece
                piece = Piece(current_piece.index + 1, self.torrent.piece_length)
                self.downloaded_pieces[piece.index] = piece
                request = Request(piece.index, piece.next_block())
                self.pending_requests.append(request)
                return request
            request = Request(current_piece.index, next_offset)

        self.pending_requests.append(request)
        return request
