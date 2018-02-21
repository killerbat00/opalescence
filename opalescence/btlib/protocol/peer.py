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
    def __init__(self, queue, info_hash, peer_id, requester, on_block_cb=None):#ip, port, torrent, peer_id, requester):
        self.my_state = []
        self.peer_state = []
        self.queue = queue
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.remote_id = None
        self.reader = None
        self.writer = None
        self.requester = requester
        self._on_block_cb = on_block_cb
        self.valid_ports = [x for x in range(6881,7000)]
        self.future = asyncio.ensure_future(self.start())

    #def __str__(self):
    #    return f"{self.ip}:{self.port}"

    def cancel(self):
        """
        Cancels this peer's execution
        :return:
        """
        logger.debug(f"{self}: Cancelling and closing connections.")
        #self.requester.remove_peer(self.peer_id)
        if not self.future.done():
            self.future.cancel()
        if self.writer:
            self.writer.close()

    def stop(self):
        self.my_state.append('stopped')
        if not self.future.done():
            self.future.cancel()

    def get_next_port(self, port):
        if port == 0:
            logger.debug(f"{self}: Port 0 returned by tracker, scanning valid bittorrent ports.")
            return self.valid_ports[0]

        try:
            port_index = self.valid_ports.index(port) + 1
        except ValueError:
            port_index = 0

        if port_index > len(self.valid_ports):
            logger.debug(f"{self}: No more bittorrent ports to try.")
            raise PeerError

        logger.debug(f"{self}: Retrying on port: {self.valid_ports[port_index]}")
        return self.valid_ports[port_index]


    async def start(self):
        """
        Starts communication with the protocol and begins downloading a torrent.
        """
        # TODO: scan valid bittorrent ports (6881-6999)
            #if port == 0:
                #for port in self.valid_ports:

        try:
            ip, port = await self.queue.get()
            #port = self.get_next_port(port)

            logger.debug(f"{self}: Opening connection.")
            self.reader, self.writer = await asyncio.open_connection(
                host=ip, port=port)

            data = await self._handshake()
            self.my_state.append("choked")
            await self._interested()

            # Remove the messagereader here. Although it uses async for,
            # it waits for a message before executing the body. This means
            # that we can't currently blast the peer with requests
            # and instead only send a request when we get a message back
            # from the peer. One option would be asking the requester for a
            # number of requests for this peer.
            async for msg in MessageReader(self.reader, data):
                if "stopped" in self.my_state:
                    break
                if isinstance(msg, KeepAlive):
                    logger.debug(f"{self}: Sent {msg}")
                    pass
                elif isinstance(msg, Choke):
                    logger.debug(f"{self}: Sent {msg}")
                    self.my_state.append("choking")
                elif isinstance(msg, Unchoke):
                    logger.debug(f"{self}: Sent {msg}")
                    if "choking" in self.my_state:
                        self.my_state.remove("choking")
                elif isinstance(msg, Interested):
                    logger.debug(f"{self}: Sent {msg}")
                    self.peer_state.append("interested")
                elif isinstance(msg, NotInterested):
                    logger.debug(f"{self}: Sent {msg}")
                    if "interested" in self.peer_state:
                        self.peer_state.remove("interested")
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

                if "interested" in self.my_state:
                    if "choking" in self.peer_state:
                        await self._interested()
                    else:
                        message = self.requester.next_request(self.peer_id)
                        if not message:
                            logger.debug(
                                f"{self}: No requests available. Waiting on last pieces to trickle in."
                                f"Schedule connection close in 10s.")
                            if self.requester.pending_requests:
                                message = self.requester.pending_requests[0]
                            else:
                                # We're done?
                                message = KeepAlive()

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

        except Exception as oe:
            logger.debug(f"{self}: Exception with connection.\n{oe}")
            self.cancel()
            raise PeerError from oe

    async def _handshake(self) -> bytes:
        """
        Negotiates the initial handshake with the peer.

        :raises PeerError:
        :return: remaining data we've read from the reader
        """
        logger.debug(f"{self}: Negotiating handshake.")
        sent_handshake = Handshake(self.info_hash, self.peer_id)
        self.writer.write(sent_handshake.encode())
        await self.writer.drain()

        data = b''
        while len(data) < Handshake.msg_len:
            data = await self.reader.read(MessageReader.CHUNK_SIZE)
            if not data:
                logger.error(f"{self}: Unable to initiate handshake, no data received from peer.")
                raise PeerError

        rcvd = Handshake.decode(data[:Handshake.msg_len])

        if rcvd.info_hash != self.info_hash:
            logger.error(f"{self}: Incorrect info hash received.")
            raise PeerError

        self.remote_id = rcvd.peer_id
        #TODO: only do this check if we received dictionary model peers
        #if self.id != self.remote_id:
        #    logger.error(f"{self}: Incorrect peer id received.")
        #    raise PeerError

        return data[Handshake.msg_len:]

    async def _interested(self):
        """
        Sends the interested message to the peer.
        The peer should unchoke us after this.
        """
        logger.debug(f"{self}: Sending interested message")
        self.writer.write(Interested.encode())
        await self.writer.drain()
        self.my_state.append("interested")
