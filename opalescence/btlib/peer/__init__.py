#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../client.py

No data is currently sent to the remote peer.
"""
import asyncio
import logging

from opalescence.btlib import log_and_raise
from .messages import Handshake, KeepAlive, Choke, Unchoke, Interested, NotInterested, Have, Bitfield, \
    Request, Block, Cancel, MessageReader

logger = logging.getLogger(__name__)


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """


class Peer:
    """
    Represents a peer and provides methods for communicating with said peer.
    """

    # TODO: Add support for sending pieces to the peer

    def __init__(self, ip, port, torrent, peer_id, requester):
        self.ip = ip
        self.port = port
        self.info_hash = torrent.info_hash
        self.id = peer_id
        self.peer_id = None
        self.reader = None
        self.writer = None
        self.choking = True
        self.interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.requester = requester

    def __str__(self):
        return f"{self.ip}:{self.port}"

    async def start(self):
        """
        Starts communication with the peer and begins downloading the torrent.
        """
        # TODO: scan valid bittorrent ports (6881-6889)
        try:
            self.reader, self.writer = await asyncio.open_connection(
                host=self.ip, port=self.port)

            logger.debug(f"{self}: Opened connection.")
            data = await self.handshake()
            await self._interested()

            async for msg in MessageReader(self.reader, data):
                if isinstance(msg, KeepAlive):
                    logger.debug(f"{self}: Sent {msg}")
                elif isinstance(msg, Choke):
                    self.peer_choking = True
                    logger.debug(f"{self}: Sent {msg}")
                elif isinstance(msg, Unchoke):
                    self.peer_choking = False
                    logger.debug(f"{self}: Sent {msg}")
                elif isinstance(msg, Interested):
                    self.peer_interested = True
                    logger.debug(f"{self}: Sent {msg}")
                elif isinstance(msg, NotInterested):
                    self.peer_interested = False
                    logger.debug(f"{self}: Sent {msg}")
                elif isinstance(msg, Have):
                    self.requester.peer_has_piece(self, msg.index)
                    logger.debug(f"{self}: Has {msg}")
                elif isinstance(msg, Bitfield):
                    self.requester.peer_sent_bitfield(self, msg.bitfield)
                    logger.debug(f"{self}: Bitfield {msg.bitfield}")
                elif isinstance(msg, Request):
                    logger.debug(f"{self}: Requested {msg}")
                elif isinstance(msg, Block):
                    self.requester.peer_sent_block(msg)
                    logger.debug(f"{self}: Piece {msg}")
                elif isinstance(msg, Cancel):
                    logger.debug(f"{self}: Canceled {msg}")
                else:
                    raise PeerError("Unsupported message type.")

                if self.interested:
                    if self.peer_choking:
                        await self._interested()
                    else:
                        request = self.requester.next_request()
                        self.writer.write(request.encode())
                        await self.writer.drain()
                        logger.debug(f"Requested piece {request.index}:{request.begin}:{request.length} from {self}")

        # TODO: Narrow down exceptions that are safely consumed
        # Eat exceptions here so we'll move to the next peer.
        # We'll eventually try this peer again anyway if the number of peers is low
        except Exception as e:
            logger.debug(f"{self}: Unable to open connection.\n{e}")
            raise PeerError from e

    async def handshake(self) -> bytes:
        """
        Negotiates the initial handshake with the peer.

        :raises PeerError:
        :return: remaining data we've read from the reader
        """
        # TODO: validate the peer id we receive is the same as from the tracker
        sent_handshake = Handshake(self.info_hash, self.id)
        self.writer.write(sent_handshake.encode())
        await self.writer.drain()

        data = b''
        while len(data) < Handshake.msg_len:
            data = await self.reader.read(MessageReader.CHUNK_SIZE)
            if not data:
                log_and_raise(f"{self}: Unable to initiate handshake", logger,
                              PeerError)

        rcvd = Handshake.decode(data[:Handshake.msg_len])

        if rcvd.info_hash != self.info_hash:
            log_and_raise(f"{self}: Incorrect info hash received.", logger,
                          PeerError)

        logger.debug(f"{self}: Successfully negotiated handshake.")
        return data[Handshake.msg_len:]

    async def _interested(self):
        """
        Sends the interested message to the peer.
        The peer should unchoke us after this.
        """
        self.writer.write(Interested.encode())
        await self.writer.drain()
        self.interested = True
        logger.debug(f"Sent interested message to {self}")
