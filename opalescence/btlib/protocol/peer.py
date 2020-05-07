#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../client.py

No data is currently sent to the remote peer
"""
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
    def __init__(self, queue, info_hash, peer_id, requester, *,
                 on_conn_made_cb = None, on_conn_close_cb = None,
                 on_block_cb=None):
        self.my_state = set()
        self.peer_state = set()
        self.queue = queue
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.remote_id = None
        self.reader = None
        self.writer = None
        self.ip = None
        self.port = None
        self.requester = requester
        self._on_block_cb = on_block_cb
        self.on_conn_close_cb = on_conn_close_cb
        self.on_conn_made_cb = on_conn_made_cb
        self.future = asyncio.ensure_future(self.start())
        self.started = True

    def __str__(self):
        return f"{self.ip}:{self.port}"

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return self.peer_id == other.peer_id and self.port == other.port and self.ip == other.ip and self.info_hash == other.info_hash

    def cancel(self, fire_cb):
        """
        Cancels this peer's execution
        :return:
        """
        logger.debug(f"{self}: Cancelling and closing connections.")
        self.requester.remove_peer(self.peer_id)
        self.started = False
        if self.writer:
            self.writer.close()
        if self.on_conn_close_cb and fire_cb:
            self.on_conn_close_cb(self)

    def restart(self):
        if not self.started:
            self.future = asyncio.ensure_future(self.start())

    async def start(self):
        """
        Starts communication with the protocol and begins downloading a torrent.
        """
        try:
            self.ip, self.port = await self.queue.get()

            logger.debug(f"{self}: Opening connection.")
            self.reader, self.writer = await asyncio.open_connection(
                host=self.ip, port=self.port)#, local_addr=('localhost', self.local_port))

            if not await self._handshake():
                self.cancel(True)
                return

            self.on_conn_made_cb(self)

            self.my_state.add("choked")
            await self._interested()

            asyncio.ensure_future(self.send_msgs())

            #TODO: Decouple message reading and sending. We should continue to send keepalive messages
            #TODO: for a reasonable amount of time until we're sure the peer can't send us anything.
            mr = MessageReader(self.reader)
            async for msg in mr:
                if "stopped" in self.my_state:
                    break
                if isinstance(msg, KeepAlive):
                    logger.debug(f"{self}: Sent {msg}")
                    pass
                elif isinstance(msg, Choke):
                    logger.debug(f"{self}: Sent {msg}")
                    self.my_state.add("choked")
                elif isinstance(msg, Unchoke):
                    logger.debug(f"{self}: Sent {msg}")
                    if "choked" in self.my_state:
                        self.my_state.remove("choked")
                elif isinstance(msg, Interested):
                    # we don't do anything with this right now
                    logger.debug(f"{self}: Sent {msg}")
                    self.peer_state.add("interested")
                elif isinstance(msg, NotInterested):
                    logger.debug(f"{self}: Sent {msg}")
                    if "interested" in self.peer_state:
                        self.peer_state.remove("interested")
                elif isinstance(msg, Have):
                    logger.debug(f"{self}: {msg}")
                    self.requester.add_available_piece(self.remote_id, msg.index)
                elif isinstance(msg, Bitfield):
                    logger.debug(f"{self}: {msg}")
                    self.requester.add_peer_bitfield(self.remote_id, msg.bitfield)
                elif isinstance(msg, Request):
                    logger.debug(f"{self}: Requested {msg}")
                elif isinstance(msg, Block):
                    logger.debug(f"{self}: {msg}")
                    self._on_block_cb(msg)
                elif isinstance(msg, Cancel):
                    logger.debug(f"{self}: {msg}")
                else:
                    raise PeerError("Unsupported message type.")

        except asyncio.CancelledError as ce:
            self.cancel(False)
            raise asyncio.CancelledError from ce
        except Exception as oe:
            logger.debug(f"{self}: Exception with connection.\n{oe}")
            self.cancel(True)
            raise PeerError from oe

    async def send_msgs(self):
        while self.started:
            try:
                if "interested" in self.my_state and not "choked" in self.my_state:
                    message = self.requester.next_request(self.remote_id)
                    if message:
                        logger.debug(f"{self.peer_id}: {message}")
                        self.writer.write(message.encode())
                        await self.writer.drain()
                        await asyncio.sleep(.01)
                    #if not message:
                    #    logger.debug(
                    #        f"{self}: No requests available. Waiting on last pieces to trickle in."
                    #        f"Schedule connection close in 10s.")
                    #    if self.requester.pending_requests:
                    #        message = self.requester.pending_requests[0]
                    #    else:
                    #        # We're done?
                    #        message = KeepAlive()
            except asyncio.CancelledError as ce:
                self.cancel(False)
                raise asyncio.CancelledError from ce
            except Exception as oe:
                logger.debug(f"{self}: Exception with connection.\n{oe}")
                self.cancel(True)
                raise PeerError from oe

    async def _handshake(self) -> bool:
        """
        Negotiates the initial handshake with the peer.

        :raises PeerError:
        :return: remaining data we've read from the reader
        """
        logger.debug(f"{self}: Negotiating handshake.")
        sent_handshake = Handshake(self.info_hash, self.peer_id)
        self.writer.write(sent_handshake.encode())
        await self.writer.drain()

        try:
            data = await self.reader.readexactly(Handshake.msg_len)
        except asyncio.IncompleteReadError as ire:
            logger.error(f"{self}: Unable to initiate handshake, no data received from peer.")
            return False

        rcvd = Handshake.decode(data[:Handshake.msg_len])

        if rcvd.info_hash != self.info_hash:
            logger.error(f"{self}: Incorrect info hash received.")
            raise PeerError

        self.remote_id = rcvd.peer_id
        return True

    async def _interested(self):
        """
        Sends the interested message to the peer.
        The peer should unchoke us after this.
        """
        logger.debug(f"{self}: Sending interested message")
        self.writer.write(Interested.encode())
        await self.writer.drain()
        self.my_state.add("interested")
