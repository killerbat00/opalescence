#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""
import hashlib
import io
import logging

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
        self.piece_length = torrent.piece_length
        self.buffer = io.BytesIO()

    def write(self, piece: Piece):
        """
        Writes the piece's data to the buffer
        """
        offset = piece.index * self.piece_length
        try:
            self.buffer.seek(offset, 0)
            self.buffer.write(piece.data)
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

    def peer_has_piece(self, peer: Peer, pc_index: int) -> None:
        """
        Sent when a peer has a piece of the torrent.

        :param peer:     The peer who has the piece
        :param pc_index: the index of the piece
        """
        self.available_pieces[pc_index].add(peer)

    def peer_sent_bitfield(self, peer: Peer, bitfield: bitstring.BitArray) -> None:
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer:     The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        if not self.bitfield:
            self.bitfield = bitstring.BitArray(length=len(bitfield))

        for i, b in enumerate(bitfield):
            if b:
                self.available_pieces[i].add(peer)

    def remove_peer(self, peer: Peer) -> None:
        """
        Removes a peer from this requester's data structures in the case that our communication
        with that peer has stopped

        :param peer: peer to remove
        """
        for _, peer_set in self.available_pieces.items():
            peer_set.discard(peer)

    def peer_sent_block(self, block: Block) -> None:
        """
        Called when we've received a block from the remote peer.
        First, see if there are other blocks from that piece already downloaded.
        If so, add this block to the piece and pend a request for the remaining blocks
        that we would need.

        :param block: The piece message with the data and e'erthang
        """
        if block.index in self.downloaded_pieces:
            pc = self.downloaded_pieces.get(block.index)
        else:
            pc = Piece(block.index, self.torrent.piece_length)
            self.downloaded_pieces[block.index] = pc

        pc.add_block(block)
        if not pc.complete:
            self.pending_requests.append(Request(block.index, pc.offset))
        else:
            pc.data.seek(0)
            pc_data = pc.data.read()
            pc_hash = hashlib.sha1(pc_data).digest()
            if pc_hash != self.torrent.pieces[pc.index]:
                logger.debug(f"Received piece doesn't match expected hash {pc.index}")
            else:
                self.bitfield[pc.index] = 1
                # self.pc_writer.write(pc)

    def next_request(self) -> Request:
        """
        Requests the next block we need.
        """
        if self.pending_requests:
            return self.pending_requests.pop()

        if not self.downloaded_pieces:
            return Request(0, 0)

        last_index = list(self.downloaded_pieces.keys())[-1]
        last_piece = self.downloaded_pieces.get(last_index)

        if not last_piece:
            return Request(last_index, 0)

        if not last_piece.complete:
            self.pending_requests.append(Request(last_piece.index, last_piece.offset))
            return self.next_request()

        return Request(last_piece.index + 1, 0)
