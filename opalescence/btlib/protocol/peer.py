# -*- coding: utf-8 -*-

"""
Support for basic communication with a peer.
The piece-requesting and saving strategies are in piece_handler.py
The coordination with peers is handled in ../download.py

No data is currently sent to the remote peer.
"""

from __future__ import annotations

__all__ = ["PeerConnectionStats", "PeerConnectionPool"]

import asyncio
import dataclasses
import struct
from logging import getLogger
from typing import Optional

from .errors import PeerError, NonSequentialBlockError
from .messages import *
from .metainfo import MetaInfoFile
from .peer_info import PeerInfo
from .piece_handler import PieceRequester

logger = getLogger(__name__)


@dataclasses.dataclass
class PeerConnectionStats:
    bytes_uploaded: int = 0
    bytes_downloaded: int = 0
    torrent_bytes_downloaded: int = 0
    torrent_bytes_wasted: int = 0


class PeerConnectionPool:
    """
    Manages a number of `PeerConnection`s.
    """

    def __init__(self, client_info: PeerInfo, meta_info: MetaInfoFile,
                 peer_queue: asyncio.Queue, piece_queue: asyncio.Queue,
                 num_peers: int):
        self.client_info = client_info
        self.torrent = meta_info
        self.peer_queue = peer_queue
        self.max_num_peers = num_peers
        self.requester = PieceRequester(self.torrent)
        self.stats = PeerConnectionStats()
        self.peers: list[Optional[PeerConnection]] = []
        self.piece_queue = piece_queue

        self.start()

    def start(self):
        """
        Creates and starts all `PeerConnection`s in this pool.
        """
        if len(self.peers) != 0:
            return

        self.peers = [
            PeerConnection(self.client_info, self.torrent, self.requester,
                           self.peer_queue, self.piece_queue, self.stats)
            for _ in range(self.max_num_peers)]

    def stop(self):
        """
        Stops all `PeerConnection`s forever.
        """
        for peer in self.peers:
            peer.stop_forever()

    @property
    def num_connected(self):
        """
        :return: The number of currently connected peers.
        """
        return len([peer for peer in self.peers if peer.peer is not None])


class PeerConnection:
    """
    Represents a peer and provides methods for communicating with that peer.
    """

    # TODO: Add support for sending pieces to the peer
    def __init__(self, local_peer, torrent, requester, peer_queue, piece_queue, stats):
        self.local = PeerInfo.from_instance(local_peer)
        self.torrent = torrent
        self.peer_queue = peer_queue
        self.peer: Optional[PeerInfo] = None

        self._requester: PieceRequester = requester
        self._msg_to_send_q: asyncio.Queue = asyncio.Queue()
        self._piece_queue: asyncio.Queue = piece_queue
        self._stop_forever = False
        self._stats = stats

        self.task = asyncio.create_task(self.download(), name="[WAITING] PeerConnection")

    def __str__(self):
        if not self.peer:
            return f"{self.task.get_name()}:{self.torrent.info_hash}"
        return f"{self.task.get_name()}:{self.torrent.info_hash}"

    def __repr__(self):
        return str(self)

    def __eq__(self, other: PeerConnection):
        return hash(self) == hash(other)

    def stop_forever(self):
        """
        Stop this `PeerConnection` forever and prevent it from connecting
        to new peers or exchanging messages.
        """
        self._stop_forever = True
        if self.task and not self.task.cancelled():
            self.task.cancel()

    def reset(self):
        """
        If this peer is connected, resets the peer connection so this
        `PeerConnection` will connect to a new peer.
        """
        if not self.peer:
            return

        if self.task and not self.task.cancelled():
            self.task.cancel()

    async def download(self):
        """
        This coroutine is scheduled as a task when the `PeerConnection` is
        initialized. It is responsible for consuming a peer connection from
        the queue and exchanging BitTorrent protocol messages with that queue.
        The `PeerConnection` will reset itself on any error until its
        been told to stop forever.
        """
        while not self._stop_forever:
            try:
                peer_info = await self.peer_queue.get()
                if not peer_info or self._stop_forever:
                    continue

                self.peer = peer_info
                self.task.set_name(f"{self.peer}")

                logger.info("%s: Opening connection with peer." % self)
                # TODO: When we start allowing peers to connect to us,
                #       we'll need to listen on a socket rather than
                #       just connecting with the peer.
                async with PeerMessenger(self.peer, self._stats) as messenger:
                    if not await self._handshake(messenger):
                        continue

                    if self._stop_forever:
                        continue

                    produce_task = asyncio.create_task(self._produce(messenger),
                                                       name=f"{self}:produce")
                    consume_task = asyncio.create_task(self._consume(messenger),
                                                       name=f"{self}:consume")
                    await asyncio.gather(produce_task, consume_task)

            except Exception as exc:
                logger.error("%s: %s received in download." % (self, type(exc).__name__))
            except BaseException as bexc:
                logger.error("%s: %s received in download." % (self, type(bexc).__name__))
                self._stop_forever = True
            finally:
                logger.info("%s: Closing connection with peer." % self)
                if self.peer:
                    self._requester.remove_peer(self.peer)
                self.peer = None

                if not self._stop_forever:
                    logger.info("%s: Resetting peer connection." % self)
                    self.local.reset_state()
                    self._msg_to_send_q = asyncio.Queue()
                    self.task.set_name("[WAITING] PeerConnection")
        logger.debug("%s: Stopped forever" % self)

    async def _consume(self, messenger: PeerMessenger):
        """
        Iterates through messages we've received from the peer after the
        initial handshake, updating state, queuing up responses, and
        handling downloaded blocks as appropriate.

        :param messenger: The `PeerMessenger` that receives data the peer sends.
        :raises PeerError: on any exception
        """
        try:
            async for msg in messenger:
                if self._stop_forever or self._requester.torrent.complete:
                    # TODO: don't stop forever if we're complete.
                    #       We may want to continue seeding.
                    #       at minimum, lose interest in the peer.
                    break

                logger.info("%s: Sent %s" % (self, msg))

                if isinstance(msg, Choke):
                    self.peer.choking = True
                    self._requester.remove_requests_for_peer(self.peer)
                    while not self._msg_to_send_q.empty():
                        self._msg_to_send_q.get_nowait()
                elif isinstance(msg, Unchoke):
                    self.peer.choking = False
                    if self.local.interested:
                        if not self._requester.fill_peer_request_queue(self.peer,
                                                                       self._msg_to_send_q):
                            if self._msg_to_send_q.empty():
                                logger.debug("%s: Unchoked us and we're interested, "
                                             "but we don't have any requests to send.")
                                raise PeerError
                elif isinstance(msg, Interested):
                    self.peer.interested = True
                    # TODO: we don't send blocks to the peer
                elif isinstance(msg, NotInterested):
                    self.peer.interested = False
                    # TODO: we don't send blocks to the peer
                elif isinstance(msg, Have):
                    self._requester.add_available_piece(self.peer, msg.index)
                    if self._requester.peer_is_interesting(self.peer):
                        if not self.local.interested:
                            self._msg_to_send_q.put_nowait(Interested())
                elif isinstance(msg, Bitfield):
                    self._requester.add_peer_bitfield(self.peer, msg.bitfield)
                    if self._requester.peer_is_interesting(self.peer):
                        if not self.local.interested:
                            self._msg_to_send_q.put_nowait(Interested())
                elif isinstance(msg, Request):
                    # TODO: we don't send blocks to the peer
                    pass
                elif isinstance(msg, Block):
                    self._received_block(msg)
                    if self.torrent.complete:
                        self.stop_forever()
                        break

                    if not self._requester.fill_peer_request_queue(self.peer,
                                                                   self._msg_to_send_q):
                        if self._msg_to_send_q.empty():
                            logger.debug("%s: No more requests for peer." % self.peer)
                            raise PeerError
                elif isinstance(msg, Cancel):
                    pass
        except Exception as exc:
            raise PeerError from exc

    def _received_block(self, block: Block):
        """
        Called when we've received a block from the remote peer.
        First, see if there are other blocks from that piece already downloaded.
        If so, add this block to the piece and pend a request for the remaining blocks
        that we would need.

        :param block: The piece message with the data and e'erthang
        """
        if not self.peer or self._stop_forever or not block or not block.data:
            return

        block_size = len(block.data)

        if block.index >= len(self.torrent.pieces):
            logger.debug("Disregarding. Piece %s does not exist." % block.index)
            self._stats.torrent_bytes_wasted += block_size
            return

        piece = self.torrent.pieces[block.index]
        if piece.complete:
            logger.debug("Disregarding. I already have %s" % block)
            self._stats.torrent_bytes_wasted += block_size
            return

        # Remove the pending requests for this block if there are any
        if not self._requester.remove_requests_for_block(self.peer, block):
            logger.debug("Disregarding. I did not request %s" % block)
            self._stats.torrent_bytes_wasted += block_size
            return

        try:
            piece.add_block(block)
        except NonSequentialBlockError:
            # TODO: Handle non-sequential blocks?
            logger.error("Block begin index is non-sequential for: %s" % block)
            self._stats.torrent_bytes_wasted += block_size
            return

        self._stats.torrent_bytes_downloaded += block_size

        if piece.complete:
            self._piece_complete(piece.index)

    def _piece_complete(self, piece_index):
        """
        Called when the last block of a piece has been received.
        Validates the piece hash matches, writes the data, and marks the
        piece complete.

        :param piece_index: the index of the completed piece.
        """
        piece = self.torrent.pieces[piece_index]
        if not piece.complete:
            return

        h = piece.hash()
        if h != self.torrent.piece_hashes[piece.index]:
            logger.error(
                "Hash for received piece %s doesn't match. Received: %s\tExpected: %s" %
                (piece.index, h, self.torrent.piece_hashes[piece.index]))
            piece.reset()
            self._stats.torrent_bytes_wasted += piece.length
        else:
            logger.info("Completed piece received: %s" % piece)
            self._requester.remove_requests_for_piece(piece.index)
            self._piece_queue.put_nowait(piece)

    async def _produce(self, messenger):
        """
        Sends messages to the peer as they become available in the message
        queue. We wait 60 seconds when trying to send the next message. If we
        don't get a message in those 60 seconds, we send a KeepAlive.

        :param messenger: The `PeerMessenger` to write data to the peer.
        :raises PeerError: on any exception.
        """
        while not self._stop_forever:
            try:
                msg = await self._msg_to_send_q.get()
                if self._stop_forever:
                    break

                if isinstance(msg, Interested):
                    if self.local.interested:
                        msg = None
                    self.local.interested = True
                elif isinstance(msg, NotInterested):
                    self.local.interested = False

                if msg:
                    logger.debug(
                        "%s: Sending %s to %s" % (self.local, msg, self.peer))
                    await messenger.send(msg)

                self._msg_to_send_q.task_done()
            except Exception as exc:
                raise PeerError from exc

    async def _handshake(self, messenger: PeerMessenger) -> bool:
        """
        Negotiates the handshake with the peer.

        :param messenger: The `PeerMessenger` through which we exchange data.
        :return: True if the handshake is successful, False otherwise
        """
        if self._stop_forever:
            return False

        logger.info("%s: Negotiating handshake." % self)
        sent_handshake = Handshake(self.torrent.info_hash,
                                   self.local.peer_id_bytes)
        await messenger.send(sent_handshake)

        if self._stop_forever:
            return False

        received_handshake = await messenger.receive_handshake()

        if not received_handshake:
            logger.error("%s: Unable to initiate handshake." % self)
            return False

        if received_handshake.info_hash != self.torrent.info_hash:
            logger.error("%s: Wrong info hash. Expected: %s\tReceived: %s" % (
                self, self.torrent.info_hash,
                received_handshake.info_hash))
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
        self._connected = False

    async def _connect(self):
        """Opens the connection with the remote peer."""
        if self._connected:
            return
        self._stream_reader, self._stream_writer = await open_peer_connection(
            host=self._peer.ip, port=self._peer.port)
        self._connected = True

    async def __aenter__(self) -> PeerMessenger:
        """Opens the connection with the remote peer."""
        await self._connect()
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
        Returns the asynchronous iterator for reading messages from the
        remote peer.

        :raises `PeerError`: if disconnected.
        """
        if not self._connected:
            raise PeerError
        return self

    async def __anext__(self) -> ProtocolMessage:
        """
        :return: The next protocol message sent by the peer.
        :raises `StopAsyncIteration`: on exception or if disconnected.
        """
        if not self._connected or self._stream_reader.at_eof():
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
        if not self._connected:
            raise PeerError("Cannot send message on disconnected PeerMessenger.")
        data = msg.encode()
        self._stream_writer.write(data)
        self._stats.bytes_uploaded += len(data)
        await self._stream_writer.drain()

    async def receive_handshake(self) -> Optional[Handshake]:
        """
        Receives and decodes the handshake message sent by the peer.

        :return: Decoded handshake if successfully read, otherwise None.
        :raises `PeerError`: if disconnected.
        """
        if not self._connected:
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")

        data = await self._stream_reader.readexactly(Handshake.msg_len)
        self._stats.bytes_downloaded += Handshake.msg_len
        return Handshake.decode(data)

    async def _receive(self) -> ProtocolMessage:
        """
        Receives and decodes the next message sent by the peer.

        :return: The decoded message if successfully read.
        :raises `PeerError`: on exception or if disconnected.
        """
        if not self._connected:
            raise PeerError("Cannot receive message on disconnected PeerMessenger.")

        try:
            msg_len = struct.unpack(">I", await self._stream_reader.readexactly(4))[0]
            self._stats.bytes_downloaded += 4

            if msg_len == 0:
                return KeepAlive()

            msg_id = struct.unpack(">B", await self._stream_reader.readexactly(1))[0]
            self._stats.bytes_downloaded += 1

            if msg_id is None or (not (0 <= msg_id <= 8)):
                raise PeerError(f"{self}: Unknown message received: {msg_id}")

            # the msg_len includes 1 byte for the id
            msg_len -= 1
            if msg_len == 0:
                return MESSAGE_TYPES[msg_id].decode()

            msg_data = await self._stream_reader.readexactly(msg_len)
            self._stats.bytes_downloaded += msg_len

            return MESSAGE_TYPES[msg_id].decode(msg_data)
        except Exception as e:
            raise PeerError from e


async def open_peer_connection(host=None, port=None) -> [asyncio.StreamReader,
                                                         asyncio.StreamWriter]:
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
