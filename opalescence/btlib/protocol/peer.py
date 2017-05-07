#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../client.py

No data is currently sent to the remote peer
"""
import logging

from .messages import *

logger = logging.getLogger(__name__)


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """


class Peer:
    """
    Represents a peer and provides methods for communicating with that peer.
    """

    # TODO: Add support for sending pieces to the peer
    def __init__(self, ip, port, torrent, peer_id, requester):
        self.ip = ip
        self.port = port
        self.info_hash = torrent.info_hash
        self.id = peer_id
        self.peer_id = str(self)
        self.reader = None
        self.writer = None
        self.choking = True
        self.interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.requester = requester
        self.future = asyncio.ensure_future(self.start())

    def __str__(self):
        return f"{self.ip}:{self.port}"

    def cancel(self):
        """
        Cancels this peer's execution
        :return:
        """
        logger.debug(f"{self}: Cancelling and closing connections.")
        self.requester.remove_peer(self.peer_id)
        self.writer.close()
        if not self.future.done():
            self.future.cancel()

    async def start(self):
        """
        Starts communication with the protocol and begins downloading a torrent.
        """
        # TODO: scan valid bittorrent ports (6881-6889)
        try:
            logger.debug(f"{self}: Opening connection.")
            self.reader, self.writer = await asyncio.open_connection(
                host=self.ip, port=self.port)

            data = await self.handshake()
            await self._interested()

            # Remove the messagereader here. Although it uses async for,
            # it waits for a message before executing the body. This means
            # that we can't currently blast the peer with requests
            # and instead only send a request when we get a message back
            # from the peer. One option would be asking the requester for a
            # number of requests for this peer.
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
                    self.requester.add_available_piece(self.peer_id, msg.index)
                    logger.debug(f"{self}: Has {msg}")
                elif isinstance(msg, Bitfield):
                    self.requester.add_peer_bitfield(self.peer_id, msg.bitfield)
                    logger.debug(f"{self}: Bitfield {msg.bitfield}")
                elif isinstance(msg, Request):
                    logger.debug(f"{self}: Requested {msg}")
                elif isinstance(msg, Block):
                    self.requester.received_block(msg)
                    logger.debug(f"{self}: Piece {msg}")
                elif isinstance(msg, Cancel):
                    logger.debug(f"{self}: Canceled {msg}")
                else:
                    raise PeerError("Unsupported message type.")

                if self.interested:
                    if self.peer_choking:
                        await self._interested()
                    else:
                        message = self.requester.next_request(self.peer_id)
                        if not message:
                            logger.debug(
                                f"{self}: No requests available. Closing "
                                f"connection.")
                            self.cancel()
                            return

                        if isinstance(message, Request):
                            logger.debug(
                                f"Requested piece {message.index}:"
                                f"{message.begin}:{message.length} from {self}")
                        else:
                            logger.debug(
                                f"Cancelling piece {message.index}:"
                                f"{message.begin}:{message.length} from {self}")

                        self.writer.write(message.encode())
                        await self.writer.drain()

        except OSError as oe:
            logger.debug(f"{self}: Exception with connection.\n{oe}")
            raise PeerError from oe

    async def handshake(self) -> bytes:
        """
        Negotiates the initial handshake with the peer.

        :raises PeerError:
        :return: remaining data we've read from the reader
        """
        # TODO: validate the peerid we receive is the same as from the tracker
        logger.debug(f"{self}: Negotiating handshake.")
        sent_handshake = Handshake(self.info_hash, self.id)
        self.writer.write(sent_handshake.encode())
        await self.writer.drain()

        data = b''
        while len(data) < Handshake.msg_len:
            data = await self.reader.read(MessageReader.CHUNK_SIZE)
            if not data:
                logger.error(f"{self}: Unable to initiate handshake")
                raise PeerError

        rcvd = Handshake.decode(data[:Handshake.msg_len])

        if rcvd.info_hash != self.info_hash:
            logger.error(f"{self}: Incorrect info hash received.")
            raise PeerError

        return data[Handshake.msg_len:]

    async def _interested(self):
        """
        Sends the interested message to the peer.
        The peer should unchoke us after this.
        """
        logger.debug(f"{self}: Sending interested message")
        self.writer.write(Interested.encode())
        await self.writer.drain()
        self.interested = True
