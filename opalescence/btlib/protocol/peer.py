# -*- coding: utf-8 -*-

"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../client.py

No data is currently sent to the remote peer.
"""

from __future__ import annotations

__all__ = ["PeerConnectionStats", "PeerError", "PeerConnection"]

import asyncio
import dataclasses
import struct
from logging import getLogger
from typing import Optional

from .messages import *
from .peer_info import PeerInfo
from .piece_handler import PieceRequester

logger = getLogger(__name__)


@dataclasses.dataclass
class PeerConnectionStats:
    started: float
    uploaded: int
    downloaded: int


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """


class PeerConnection:
    """
    Represents a peer and provides methods for communicating with that peer.
    """

    # TODO: Add support for sending pieces to the peer
    def __init__(self, local_peer, info_hash: bytes, requester: PieceRequester, peer_queue: asyncio.Queue,
                 stats: PeerConnectionStats):
        self.local = PeerInfo(local_peer.ip, local_peer.port, local_peer.peer_id_bytes)
        self.info_hash: bytes = info_hash
        self.peer_queue = peer_queue
        self.peer = None
        self._requester: PieceRequester = requester
        self._msg_to_send_q: asyncio.Queue = asyncio.Queue()
        self._stop_forever = False
        self._stats = stats

        self.task = asyncio.create_task(self.download(), name="[WAITING] PeerConnection")

    def __str__(self):
        if not self.peer:
            return f"{self.task.get_name()}:{self.info_hash}"
        return f"{self.task.get_name()}:{self.info_hash}"

    def __repr__(self):
        return str(self)

    def __eq__(self, other: PeerConnection):
        return hash(self) == hash(other)

    def stop_forever(self):
        self._stop_forever = True
        if self.task:
            self.task.cancel()

    async def download(self):
        """
        :return:
        """
        while not self._stop_forever:
            try:
                peer_info = await self.peer_queue.get()
                if not peer_info or self._stop_forever:
                    continue

                self.peer = peer_info
                self.task.set_name(f"{self.peer}")

                logger.info(f"{self}: Opening connection with peer.")
                # TODO: When we start allowing peers to connect to us, we'll need to listen
                #       on a socket rather than just connecting with the peer.
                async with PeerMessenger(self.peer, self._stats) as messenger:
                    if not await self._handshake(messenger):
                        raise PeerError

                    produce_task = asyncio.create_task(self._produce(messenger), name=f"Produce Task for {self}")
                    consume_task = asyncio.create_task(self._consume(messenger), name=f"Consume Task for {self}")
                    await asyncio.gather(produce_task, consume_task)

            except Exception as exc:
                logger.error(f"{self}: {type(exc).__name__} received in download.")
            except BaseException:
                self._stop_forever = True
            finally:
                logger.info(f"{self}: Closing connection with peer.")
                self.local.reset_state()
                if not self.peer:
                    continue
                self._requester.remove_peer(self.peer.peer_id)
                if not self._stop_forever:
                    logger.info(f"{self}: Resetting peer connection.")
                    self._msg_to_send_q = asyncio.Queue()
                    self.peer = None
                    self.task.set_name("[WAITING] PeerConnection")
        logger.debug(f"{self}: Stopped forever.")

    async def _consume(self, messenger: PeerMessenger):
        """
        Iterates through messages we've received from the peer after the initial handshake,
        queuing up responses as appropriate.

        :param messenger: The `PeerMessenger` which receives data the peer sends.
        :raises PeerError: on any exception
        """
        try:
            async for msg in messenger:
                if self._stop_forever:
                    break
                logger.info(f"{self}: Sent {msg}")
                if isinstance(msg, Choke):
                    self.peer.choking = True
                    self._requester.remove_pending_requests_for_peer(self.peer.peer_id)
                elif isinstance(msg, Unchoke):
                    self.peer.choking = False
                    self._msg_to_send_q.put_nowait(self._requester.next_request_for_peer(self.peer.peer_id))
                elif isinstance(msg, Interested):
                    self.peer.interested = True
                    # TODO: we don't send blocks to the peer
                elif isinstance(msg, NotInterested):
                    self.peer.interested = False
                    # TODO: we don't send blocks to the peer
                elif isinstance(msg, Have):
                    self._requester.add_available_piece(self.peer.peer_id, msg.index)
                    if not self.local.interested:
                        self._msg_to_send_q.put_nowait(Interested())
                elif isinstance(msg, Bitfield):
                    self._requester.add_peer_bitfield(self.peer.peer_id, msg.bitfield)
                    if not self.local.interested:
                        self._msg_to_send_q.put_nowait(Interested())
                elif isinstance(msg, Request):
                    pass
                elif isinstance(msg, Block):
                    await self._requester.received_block(self.peer.peer_id, msg)
                    # TODO: better piece requesting, currently in-order tit for tat
                    self._msg_to_send_q.put_nowait(self._requester.next_request_for_peer(self.peer.peer_id))
                elif isinstance(msg, Cancel):
                    pass
            raise PeerError  # out of messages
        except Exception:
            raise

    async def _produce(self, messenger):
        """
        Sends messages to the peer as they become available in the message queue.
        We wait 60 seconds when trying to send the next message. If we don't get
        a message in those 60 seconds, we send a KeepAlive.

        :param messenger: The `PeerMessenger` via which we write data to the peer.
        :raises PeerError: on any exception.
        """
        log, msg = None, None
        while True:
            try:
                if not msg:
                    msg = await self._msg_to_send_q.get()
                    mark_done = True
                    if self._stop_forever:
                        break
                else:
                    mark_done = False

                if isinstance(msg, Interested):
                    if self.local.interested:
                        msg = None
                    self.local.interested = True
                elif isinstance(msg, NotInterested):
                    self.local.interested = False

                if msg:
                    if not log:
                        log = f"{self.local}: Sending {msg} to {self}"
                    logger.debug(log)
                    await messenger.send(msg)
                    msg, log = None, None

                if mark_done:
                    self._msg_to_send_q.task_done()

            except Exception:
                raise

    async def _handshake(self, messenger: PeerMessenger) -> bool:
        """
        Negotiates the handshake with the peer.

        :param messenger: The `PeerMessenger` through which we exchange data.
        :return: True if the handshake is successful, False otherwise
        """
        logger.info(f"{self}: Negotiating handshake.")
        sent_handshake = Handshake(self.info_hash, self.local.peer_id_bytes)
        await messenger.send(sent_handshake)
        received_handshake = await messenger.receive_handshake()
        if not received_handshake:
            logger.error(f"{self}: Unable to initiate handshake.")
            return False

        if received_handshake.info_hash != self.info_hash:
            logger.error(f"{self}: Unable in initiate handshake. Incorrect info hash received. expected: "
                         f"{self.info_hash}, received {received_handshake.info_hash}")
            return False

        if received_handshake.peer_id:
            self.peer.peer_id = received_handshake.peer_id
        return True


class PeerMessenger:
    """An async API for sending and receiving BitTorrent protocol messages.

    Wraps `asyncio.StreamReader` and `asyncio.StreamWriter`, implementing
    the async context manager and async iterator protocols.

    TODO: client vs server mode?
    """

    def __init__(self, peer, connection_stats: PeerConnectionStats):
        self._stream_reader: Optional[asyncio.StreamReader] = None
        self._stream_writer: Optional[asyncio.StreamWriter] = None
        self._peer = peer
        self._stats = connection_stats

    async def __aenter__(self) -> PeerMessenger:
        """Opens the connection with the remote peer."""
        self._stream_reader, self._stream_writer = await open_peer_connection(host=self._peer.ip, port=self._peer.port)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """
        Closes the connection with the remote peer.
        Defers exception handling to the caller.
        """
        if self._stream_writer:
            await self._stream_writer.drain()
            self._stream_writer.close()
            await self._stream_writer.wait_closed()
        return False

    def __aiter__(self) -> PeerMessenger:
        """
        :returns: The asynchronous iterator for reading messages from the remote peer.
        :raises `PeerError`: if disconnected.
        """
        if None in [self._stream_reader, self._stream_writer]:
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")
        return self

    async def __anext__(self) -> ProtocolMessage:
        """
        :return: The next protocol message sent by the peer.
        :raises `StopAsyncIteration`: on exception or if disconnected.
        """
        if self._stream_reader is None:
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")

        if self._stream_reader.at_eof():
            raise StopAsyncIteration

        try:
            return await self._receive()
        except Exception:
            raise StopAsyncIteration

    async def send(self, msg: Message) -> None:
        """
        Sends a message to the remote peer.

        :param msg: The `Message` object to encode and send.
        :raises `PeerError`: if disconnected.
        """
        if self._stream_writer is None:
            raise PeerError("Cannot send message on disconnected PeerMessenger.")
        data = msg.encode()
        self._stream_writer.write(data)
        self._stats.uploaded += len(data)
        await self._stream_writer.drain()

    async def receive_handshake(self) -> Optional[Handshake]:
        """
        Receives and decodes the handshake message sent by the peer.

        :return: Decoded handshake if successfully read, otherwise None.
        :raises `PeerError`: if disconnected.
        """
        if self._stream_reader is None or self._stream_reader.exception():
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")

        try:
            data = await self._stream_reader.readexactly(Handshake.msg_len)
        except asyncio.IncompleteReadError:
            data = await self._stream_reader.readexactly(Handshake.msg_len)
        self._stats.downloaded += Handshake.msg_len
        return Handshake.decode(data)

    async def _receive(self) -> ProtocolMessage:
        """
        Receives and decodes the next message sent by the peer.

        :return: The decoded message if successfully read.
        :raises `PeerError`: on exception or if disconnected.
        """
        if self._stream_reader is None or self._stream_reader.exception():
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")

        try:
            msg_len = struct.unpack(">I", await self._stream_reader.readexactly(4))[0]
            self._stats.downloaded += 4

            if msg_len == 0:
                return KeepAlive()

            msg_id = struct.unpack(">B", await self._stream_reader.readexactly(1))[0]
            self._stats.downloaded += 1

            if msg_id is None or (not (0 <= msg_id <= 8)):
                raise PeerError(f"{self}: Unknown message received: {msg_id}")

            msg_len -= 1  # the msg_len includes 1 byte for the id, we've consumed that already
            if msg_len == 0:
                return MESSAGE_TYPES[msg_id].decode()
            msg_data = await self._stream_reader.readexactly(msg_len)
            self._stats.downloaded += msg_len
            return MESSAGE_TYPES[msg_id].decode(msg_data)
        except Exception as e:
            raise PeerError from e


async def open_peer_connection(host=None, port=None) -> [asyncio.StreamReader, asyncio.StreamWriter]:
    """
    A wrapper for asyncio.open_connection() returning a (reader, writer) pair.
    """
    loop = asyncio.events.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(
        lambda: protocol, host, port)
    transport.set_write_buffer_limits(0)  # let the OS handle buffering
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer
