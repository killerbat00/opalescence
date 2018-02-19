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
        self.valid_ports = [x for x in range(6881,7000)]

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

    async def start(self):
        """
        Starts communication with the protocol and begins downloading a torrent.
        """
        # TODO: scan valid bittorrent ports (6881-6999)
        # TODO: Make scanning smarter
        if self.port == 0:
            self.port = self.valid_ports[0]
        else:
            self.port = self.valid_ports[self.valid_ports.index(self.port)+1]

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
                    logger.debug(f"{self}: Sent {msg}")
                    self.peer_choking = True
                elif isinstance(msg, Unchoke):
                    logger.debug(f"{self}: Sent {msg}")
                    self.peer_choking = False
                elif isinstance(msg, Interested):
                    logger.debug(f"{self}: Sent {msg}")
                    self.peer_interested = True
                elif isinstance(msg, NotInterested):
                    logger.debug(f"{self}: Sent {msg}")
                    self.peer_interested = False
                elif isinstance(msg, Have):
                    logger.debug(f"{self}: Has {msg}")
                    self.requester.add_available_piece(self.peer_id, msg.index)
                elif isinstance(msg, Bitfield):
                    logger.debug(f"{self}: Bitfield {msg.bitfield}")
                    self.requester.add_peer_bitfield(self.peer_id, msg.bitfield)
                elif isinstance(msg, Request):
                    logger.debug(f"{self}: Requested {msg}")
                elif isinstance(msg, Block):
                    logger.debug(f"{self}: Received Block {msg}")
                    self.requester.received_block(msg)
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

            self.requester.write_last_piece()
        except OSError as oe:
            logger.debug(f"{self}: Exception with connection.\n{oe}")
            await self.start()
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
