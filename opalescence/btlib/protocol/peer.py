# -*- coding: utf-8 -*-

"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../client.py

No data is currently sent to the remote peer.
"""
from __future__ import annotations

import asyncio
import struct
from logging import getLogger
from typing import Optional

from .errors import PeerError
from .messages import *
from .piece_handler import PieceRequester
from ..utils import open_peer_connection

logger = getLogger(__name__)


class PeerInfo:
    def __init__(self, ip: str, port: int, peer_id: Optional[bytes] = None):
        self.ip: str = ip
        self.port: int = port
        self._peer_id: Optional[bytes] = peer_id
        self.choking = True
        self.interested = False

    def __str__(self):
        return f"{self.ip}:{self.port}"

    @property
    def peer_id_bytes(self) -> bytes:
        if self._peer_id:
            return self._peer_id

    @property
    def peer_id(self) -> str:
        return str(self)

    @peer_id.setter
    def peer_id(self, val):
        if isinstance(val, bytes):
            self._peer_id = val


class PeerConnection:
    """
    Represents a peer and provides methods for communicating with that peer.
    """

    # TODO: Add support for sending pieces to the peer
    def __init__(self, local_peer: PeerInfo, info_hash: bytes, requester: PieceRequester, peer_queue: asyncio.Queue):
        self.local = local_peer
        self.info_hash: bytes = info_hash
        self.peer_queue = peer_queue
        self._requester: PieceRequester = requester
        self._msg_to_send_q: asyncio.Queue = asyncio.Queue()
        self._msg_receive_to: float = 10.0
        self._msg_send_to: float = 60.0
        self._task = asyncio.create_task(self.download(), name="[WAITING] PeerConnection")
        self._stop_forever = False
        self.peer: Optional[PeerInfo] = None

    def __str__(self):
        if not self.peer:
            return f"[NOPEER]:{self.local}:{self.info_hash}"
        return f"{self.peer.ip}:{self.peer.port}:{self.info_hash}"

    def __eq__(self, other: PeerConnection):
        return hash(self) == hash(other)

    def stop_forever(self):
        self._stop_forever = True
        if self._task:
            self._task.cancel()

    async def download(self):
        """
        :return:
        """
        while not self._stop_forever:
            num_timeouts = 0
            try:
                peer_info = await self.peer_queue.get()
                self._task.set_name(f"{self}")
                if not peer_info:
                    raise PeerError

                self.peer = peer_info
                self._task.set_name(f"{self}")

                logger.info(f"{self}: Opening connection with peer.")
                # TODO: When we start allowing peers to connect to us, we'll need to listen
                #       on a socket rather than just connecting with the peer.
                async with PeerMessenger(self.peer) as messenger:
                    if not await self._handshake(messenger):
                        raise PeerError

                    produce_task = asyncio.create_task(self._produce(messenger), name=f"Produce Task for {self}")
                    consume_task = asyncio.create_task(self._consume(messenger), name=f"Consume Task for {self}")
                    await asyncio.gather(produce_task, consume_task)

            except Exception as cpe:
                if isinstance(cpe, ConnectionRefusedError):
                    num_timeouts += 1
                    await asyncio.sleep(0.5)
                    continue
                elif not isinstance(cpe, asyncio.CancelledError):
                    logger.exception(f"{self}: {type(cpe).__name__} received in download.", exc_info=True)
            finally:
                if not self.peer:
                    continue
                logger.info(f"{self}: Closing connection with peer.")
                self._requester.remove_peer(self.peer.peer_id)
                self._msg_to_send_q = asyncio.Queue()
                self.peer = None
                self._task.set_name("[WAITING] PeerConnection")
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
                    # self._requester.add_peer_request(self.peer.peer_id, msg)
                elif isinstance(msg, Block):
                    await self._requester.received_block(self.peer.peer_id, msg)
                    # TODO: better piece requesting, currently in-order tit for tat
                    self._msg_to_send_q.put_nowait(self._requester.next_request_for_peer(self.peer.peer_id))
                elif isinstance(msg, Cancel):
                    pass
        except Exception as ce:
            if not isinstance(ce, asyncio.CancelledError):
                logger.exception(f"{self}: {type(ce).__name__} received in write_task:_consume.", exc_info=True)
            raise PeerError from ce

    async def _produce(self, messenger):
        """
        Sends messages to the peer as they become available in the message queue.
        We wait 60 seconds when trying to send the next message. If we don't get
        a message in those 60 seconds, we send a KeepAlive.

        :param messenger: The `PeerMessenger` via which we write data to the peer.
        :raises PeerError: on any exception.
        """
        try:
            num_timeouts = 0
            while True:
                log, msg = None, None
                try:
                    msg = await asyncio.wait_for(self._msg_to_send_q.get(), timeout=self._msg_send_to)
                    if not msg:
                        continue
                except TimeoutError:
                    num_timeouts += 1
                    log = f"{self}: No message to send #{num_timeouts}, sending KeepAlive."
                    msg = KeepAlive()
                    if num_timeouts >= 3:
                        raise PeerError(f"{self}: Too many timeouts in _produce.")

                if isinstance(msg, Choke):
                    self.local.choking = True
                    # TODO: we don't send blocks to the peer
                elif isinstance(msg, Unchoke):
                    self.local.choking = False
                    # TODO: we don't send blocks to the peer
                elif isinstance(msg, Interested):
                    if self.local.interested:
                        msg = None
                    self.local.interested = True
                elif isinstance(msg, NotInterested):
                    self.local.interested = False
                elif isinstance(msg, Have):
                    # TODO: we don't send blocks to the peer
                    pass
                elif isinstance(msg, Bitfield):
                    # TODO: we don't send blocks to the peer
                    pass
                elif isinstance(msg, Request):
                    # TODO: we don't send blocks to the peer
                    pass
                elif isinstance(msg, Block):
                    # TODO: we don't send blocks to the peer
                    pass
                elif isinstance(msg, Cancel):
                    # TODO: we don't send blocks to the peer
                    pass

                if msg:
                    if not log:
                        log = f"{self.local}: Sending {msg} to {self}"
                    logger.debug(log)
                    await messenger.send(msg)

                self._msg_to_send_q.task_done()

        except Exception as ce:
            if not isinstance(ce, asyncio.CancelledError):
                logger.exception(f"{self}: {type(ce).__name__} received in produce.", exc_info=True)
            raise PeerError from ce

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

    def __init__(self, peer: PeerInfo):
        self._stream_reader: Optional[asyncio.StreamReader] = None
        self._stream_writer: Optional[asyncio.StreamWriter] = None
        self._peer = peer

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
        except PeerError:
            raise StopAsyncIteration

    async def send(self, msg: Message) -> None:
        """
        Sends a message to the remote peer.

        :param msg: The `Message` object to encode and send.
        :raises `PeerError`: if disconnected.
        """
        if self._stream_writer is None:
            raise PeerError("Cannot send message on disconnected PeerMessenger.")
        self._stream_writer.write(msg.encode())
        await self._stream_writer.drain()

    async def receive_handshake(self) -> Optional[Handshake]:
        """
        Receives and decodes the handshake message sent by the peer.

        :return: Decoded handshake if successfully read, otherwise None.
        :raises `PeerError`: if disconnected.
        """
        if self._stream_reader is None or self._stream_reader.exception():
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")

        data = await self._stream_reader.readexactly(Handshake.msg_len)
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

            if msg_len == 0:
                return KeepAlive()

            msg_id = struct.unpack(">B", await self._stream_reader.readexactly(1))[0]

            if msg_id is None or (not (0 <= msg_id <= 8)):
                raise PeerError(f"{self}: Unknown message received: {msg_id}")

            msg_len -= 1  # the msg_len includes 1 byte for the id, we've consumed that already
            if msg_len == 0:
                return MESSAGE_TYPES[msg_id].decode()
            msg_data = await self._stream_reader.readexactly(msg_len)
            return MESSAGE_TYPES[msg_id].decode(msg_data)
        except Exception as e:
            logger.exception(f"{self}: Exception encountered...", exc_info=True)
            raise PeerError from e
