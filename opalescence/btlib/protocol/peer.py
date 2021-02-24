# -*- coding: utf-8 -*-

"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../client.py

No data is currently sent to the remote peer.
"""
from __future__ import annotations

__all__ = ['PeerConnection', 'PeerInfo', 'PeerError']

import asyncio
from logging import getLogger
from typing import Optional

from .errors import PeerError
from .messages import *
from .piece_handler import PieceRequester

logger = getLogger(__name__)


async def open_peer_connection(host=None, port=None, **kwds):
    """
    A wrapper for asyncio.open_connection() returning a (reader, writer) pair.
    """
    loop = asyncio.events.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(
        lambda: protocol, host, port, **kwds)
    transport.set_write_buffer_limits(0)  # let the OS handle buffering
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer


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
            reader, writer = None, None
            try:
                peer_info = await self.peer_queue.get()
                if not peer_info:
                    raise PeerError

                self.peer = peer_info
                self._task.set_name(f"{self}")

                logger.info(f"{self}: Opening connection with peer.")
                # TODO: When we start allowing peers to connect to us, we'll need to listen
                #       on a socket rather than just connecting with the peer.
                reader, writer = await asyncio.wait_for(open_peer_connection(host=self.peer.ip, port=self.peer.port),
                                                        timeout=self._msg_send_to)

                if not await asyncio.wait_for(self._handshake(reader, writer), timeout=self._msg_send_to):
                    raise PeerError

                produce_task = asyncio.create_task(self._produce(writer), name=f"Produce Task for {self}")
                consume_task = asyncio.create_task(self._consume(reader), name=f"Consume Task for {self}")
                await asyncio.gather(produce_task, consume_task)

            except Exception as cpe:
                if not isinstance(cpe, asyncio.CancelledError):
                    logger.exception(f"{self}: {type(cpe).__name__} received in download.", exc_info=True)
            finally:
                if not self.peer:
                    continue
                logger.info(f"{self}: Closing connection with peer.")
                self._requester.remove_peer(self.peer.peer_id)
                self._msg_to_send_q = asyncio.Queue()
                if writer:
                    await writer.drain()
                    writer.close()
                    await asyncio.sleep(0)
                self.peer = None
                self._task.set_name("[WAITING] PeerConnection")
        logger.debug(f"{self}: Stopped forever.")

    async def _consume(self, reader):
        """
        Iterates through messages we've received from the peer after the initial handshake,
        queuing up responses as appropriate.

        :param reader: The StreamReader in which the peer sends data.
        :raises PeerError: on any exception
        """
        try:
            sentinel = object()
            num_timeouts = 0
            async for msg in MessageReader(reader, sentinel, self._msg_receive_to):
                if msg is sentinel:
                    num_timeouts += 1
                    logger.debug(f"{self}: Timeout #{num_timeouts} received...")
                    if num_timeouts >= 6:
                        raise PeerError(f"{self}: Too many timeouts in _consume.")

                logger.debug(f"{self}: Sent {msg}")
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
                logger.error(f"{self}: {type(ce).__name__} received in write_task:_consume.")
                logger.exception(ce, exc_info=True)
            raise PeerError from ce

    async def _produce(self, writer):
        """
        Sends messages to the peer as they become available in the message queue.
        We wait 60 seconds when trying to send the next message. If we don't get
        a message in those 60 seconds, we send a KeepAlive.

        :param writer: The StreamWriter on which we write data to the peer.
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
                    writer.write(msg.encode())
                    await writer.drain()

                self._msg_to_send_q.task_done()

        except Exception as ce:
            if not isinstance(ce, asyncio.CancelledError):
                logger.exception(f"{self}: {type(ce).__name__} received in produce.", exc_info=True)
            raise PeerError from ce

    async def _handshake(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        """
        Negotiates the handshake with the peer.

        :param reader: The StreamReader on which the peer sends data.
        :param writer: The StreamWriter on which we write data to the peer.
        :return: True if the handshake is successful, False otherwise
        """
        logger.debug(f"{self}: Negotiating handshake.")
        sent_handshake = Handshake(self.info_hash, self.local.peer_id_bytes)
        writer.write(sent_handshake.encode())
        await writer.drain()

        try:
            data = await reader.readexactly(Handshake.msg_len)
        except asyncio.IncompleteReadError as ire:
            logger.error(f"{self}: Unable to initiate handshake, read: {len(ire.partial)}, expected: {ire.expected}")
            return False

        received = Handshake.decode(data)
        if received.info_hash != self.info_hash:
            logger.error(f"{self}: Unable in initiate handshake. Incorrect info hash received. expected: "
                         f"{self.info_hash}, received {received.info_hash}")
            return False

        if received.peer_id:
            self.peer.peer_id = received.peer_id
        return True
