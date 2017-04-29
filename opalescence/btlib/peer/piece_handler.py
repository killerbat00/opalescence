#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""
import hashlib
import io
import logging

import bitstring as bitstring

from . import Peer
from .messages import Request, Block, Piece
from ..torrent import Torrent

logger = logging.getLogger(__name__)


class Writer:
    """
    Writes piece data to temp memory for now.
    Will eventually flush data to the disk.
    """

    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.buffer = io.BytesIO()

    def write(self, piece: Piece):
        """
        Writes the piece's data to the buffer
        """
        pc_offset = piece.index * piece.length
        try:
            self.buffer.seek(pc_offset, 0)
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
        self.pieces = {i: set() for i in range(self.total_pieces)}
        self.pending_requests = []
        self.partial_pieces = {}

    def peer_has_pc(self, peer: Peer, pc_index: int) -> None:
        """
        Sent when a peer has a piece of the torrent.

        :param peer:     The peer who has the piece
        :param pc_index: the index of the piece
        """
        self.pieces[pc_index].add(peer)

    def peer_sent_pc(self, pc_msg: Block) -> None:
        """
        Called when we've received a block from the remote peer.

        :param pc_msg: The piece message with the data and e'erthang
        """
        msg_data_len = len(pc_msg.data)
        if pc_msg.begin == 0 and msg_data_len == self.piece_length:
            # we have a full piece!
            pc_hash = hashlib.sha1(pc_msg.data).digest()
            if pc_hash != self.torrent.pieces[pc_msg.index]:
                logger.debug(f"Piece received from peer doesn't match expected hash.")
                return
            pc = Piece(pc_msg.index, self.piece_length)
            pc.data = pc_msg.data
            self.bitfield[pc_msg.index] = 1
            self.pc_writer.write(pc)
        else:
            # we need more blocks of that piece
            offset = pc_msg.begin + msg_data_len
            needed_length = self.piece_length - offset
            self.partial_pieces[pc_msg.index] = pc_msg
            while needed_length > 0:
                if needed_length > Request.size:
                    self.pending_requests.append(Request(pc_msg.index, self.piece_length - Request.size))

            if needed_length > Request.size:
                self.pending_requests.append(Request(pc_msg.index, offset))
                self.pending_requests
                self.pending_requests.append(Request(pc_msg.index))
            self.pending_requests.append(Request(pc_msg.index, offset, needed_length))

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
                self.pieces[i].add(peer)

    def next_request(self) -> Request:
        """
        Requests the next block we need.
        """
        if self.pending_requests:
            return self.pending_requests.pop()
        else:
            for i, b in enumerate(self.bitfield):
                if b == 0:
                    return Request(i, 0)

    def remove_peer(self, peer: Peer) -> None:
        """
        Removes a peer from this requester's data structures in the case that our communication
        with that peer has stopped

        :param peer: peer to remove
        """
        for _, peer_set in self.pieces.items():
            peer_set.discard(peer)
