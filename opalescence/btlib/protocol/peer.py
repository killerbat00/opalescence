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
import collections
import dataclasses
import struct
from logging import getLogger
from typing import Optional

from .errors import PeerError
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
        self.stats = PeerConnectionStats()
        self.requester = PieceRequester(self.torrent, self.stats)
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
        self._messages_to_send: asyncio.Queue = asyncio.Queue()
        self._completed_pieces: asyncio.Queue = piece_queue
        self._stats = stats

        self.task = asyncio.create_task(self.download(), name="[WAITING] PeerConnection")
        self._stop_forever = False
        self._last_message_sent = None
        self._last_message_received = None
        self._recently_sent = collections.deque([], maxlen=10)
        self._peer_connected_event = asyncio.Event()

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
        if self.task and not self.task.done():
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
            tasks = []
            reader, writer = None, None
            received_msg_q = asyncio.Queue()
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
                reader, writer = await open_connection(peer_info.ip, peer_info.port)
                if not await self.negotiate_handshake(reader, writer):
                    continue

                if self._stop_forever:
                    continue

                tasks.append(asyncio.create_task(read_messages_task(reader,
                                                                    received_msg_q,
                                                                    self._stats),
                                                 name=f"{self}:read"))
                tasks.append(asyncio.create_task(self._produce(writer),
                                                 name=f"{self}:produce"))
                tasks.append(asyncio.create_task(self._consume(received_msg_q),
                                                 name=f"{self}:consume"))
                tasks.append(asyncio.create_task(self._monitor_connection(),
                                                 name=f"{self}:monitor"))
                await asyncio.gather(*tasks)
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
                await close_connection(writer)

                for t in tasks:
                    if not t.done():
                        t.cancel()

                await asyncio.gather(*tasks, return_exceptions=True)

                if not self._stop_forever:
                    logger.info("%s: Resetting peer connection." % self)
                    self.local.reset_state()
                    self._messages_to_send = asyncio.Queue()
                    self._last_message_sent = None
                    self._recently_sent = collections.deque([], maxlen=10)
                    self.task.set_name("[WAITING] PeerConnection")

        logger.debug("%s: Stopped forever" % self)

    async def _monitor_connection(self):
        """
        Monitors the health of this peer connection, sending
        KeepAlive and resending stale Requests.
        """
        started_at = asyncio.get_event_loop().time()
        num_keep_alive = 0
        max_keep_alive = 2
        check_requests = True

        while not self._stop_forever:
            if not self.peer:
                break

            now = asyncio.get_event_loop().time()

            # No messages sent or received yet, sleep for now.
            if not self._last_message_sent or not self._last_message_received:
                if now - started_at >= 10:
                    raise PeerError("%s: No messages exchanged with peer for 10 "
                                    "seconds." % self)
                await asyncio.sleep(.5)
                continue

            last_msg_diff = now - self._last_message_sent
            keep_alive_diff = now - self._last_message_received
            if keep_alive_diff >= 30:
                num_keep_alive += 1
                if num_keep_alive >= max_keep_alive:
                    raise PeerError("%s: Sent 2 KeepAlives with no response. Closing "
                                    "connection." % self)
                asyncio.create_task(self._messages_to_send.put(KeepAlive()))

            if last_msg_diff >= 2 and check_requests:
                added = False
                outstanding = self._requester.peer_outstanding_requests(self.peer)
                if self.local.interested and outstanding:
                    logger.debug(
                        "%s: Last message sent to the peer > 2 seconds ago. "
                        "Attempting to resend outstanding requests." % self)
                    for msg in outstanding:
                        if isinstance(msg, Request) and msg.is_stale(now):
                            msg.num_retries += 1
                            if msg.num_retries >= 6:
                                if msg.num_retries == 6:
                                    logger.debug(
                                        "%s: Retried request max # of times." % self)
                                continue
                            asyncio.create_task(self._messages_to_send.put(msg))
                            added = True

                    if not added:
                        check_requests = False
            await asyncio.sleep(.5)

    async def _consume(self, received_msg_q: asyncio.Queue):
        """
        Iterates through messages we've received from the peer after the
        initial handshake, updating state, queuing up responses, and
        handling downloaded blocks as appropriate.

        :param received_msg_q: Queue from which to read received messages.

        :raises PeerError: on any exception
        """
        try:
            while not self._stop_forever:
                if not received_msg_q:
                    raise PeerError("%s: No received message queue." % self)

                msg = await received_msg_q.get()
                if self._stop_forever or self._requester.torrent.complete:
                    # TODO: don't stop forever if we're complete.
                    #       We may want to continue seeding.
                    #       at minimum, lose interest in the peer.
                    break

                logger.info("%s: Sent %s" % (self, msg))
                self._last_message_received = asyncio.get_event_loop().time()

                if isinstance(msg, Choke):
                    self.peer.choking = True
                    self._requester.remove_requests_for_peer(self.peer)
                    # Decide if we should only purge requests?
                elif isinstance(msg, Unchoke):
                    self.peer.choking = False
                    if self.local.interested:
                        if not self._requester.fill_peer_request_queue(self.peer,
                                                                       self._messages_to_send):
                            logger.debug("%s: Unchoked us and we're interested, "
                                         "but we don't have any requests to send.")
                            raise PeerError
                elif isinstance(msg, Have):
                    self._requester.add_available_piece(self.peer, msg.index)
                    if self._requester.peer_is_interesting(self.peer):
                        if not self.local.interested:
                            asyncio.create_task(self._messages_to_send.put(Interested()))
                elif isinstance(msg, Bitfield):
                    self._requester.add_peer_bitfield(self.peer, msg.bitfield)
                    if self._requester.peer_is_interesting(self.peer):
                        if not self.local.interested:
                            asyncio.create_task(self._messages_to_send.put(Interested()))
                elif isinstance(msg, Block):
                    piece = self._requester.peer_received_block(msg, self.peer)
                    if piece:
                        self._piece_complete(piece.index)

                    if self.torrent.complete:
                        self.stop_forever()
                        break

                    if not self._requester.fill_peer_request_queue(self.peer,
                                                                   self._messages_to_send):
                        logger.debug("%s: No more requests for peer." % self.peer)
                        # raise PeerError
        except Exception as exc:
            raise PeerError from exc

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
        asyncio.create_task(self._completed_pieces.put(piece))
        asyncio.create_task(self._messages_to_send.put(Have(piece.index)))

    async def _produce(self, writer):
        """
        Sends messages to the peer as they become available in the message
        queue. We wait 60 seconds when trying to send the next message. If we
        don't get a message in those 60 seconds, we send a KeepAlive.

        :raises PeerError: on any exception.
        """
        while not self._stop_forever:
            try:
                msg = await self._messages_to_send.get()
                if self._stop_forever:
                    break

                if isinstance(msg, Interested):
                    if self.local.interested:
                        msg = None
                    self.local.interested = True
                elif isinstance(msg, NotInterested):
                    self.local.interested = False
                elif isinstance(msg, Request):
                    msg.requested_at = asyncio.get_event_loop().time()

                if msg:
                    logger.debug("%s: Sending %s to %s" % (self.local, msg, self.peer))

                    data = msg.encode()
                    if not data:
                        raise PeerError("No data encoded.")

                    writer.write(data)
                    self._stats.bytes_uploaded += len(data)
                    self._last_message_sent = asyncio.get_event_loop().time()
                    self._recently_sent.append(msg)
                    asyncio.create_task(writer.drain())

                self._messages_to_send.task_done()
            except Exception as exc:
                raise PeerError from exc

    async def negotiate_handshake(self,
                                  reader: asyncio.StreamReader,
                                  writer: asyncio.StreamWriter) -> bool:
        """
        Negotiates the handshake with the peer.

        :param reader: `StreamReader` to read the handshake from.
        :param writer: `StreamWriter` to write the handshake to

        :return: True if the handshake is successful, False otherwise
        """
        if self._stop_forever:
            return False

        logger.info("%s: Negotiating handshake." % self)
        sent_handshake = Handshake(self.torrent.info_hash,
                                   self.local.peer_id_bytes).encode()
        if not sent_handshake:
            return False
        writer.write(sent_handshake)
        self._stats.bytes_uploaded += len(sent_handshake)
        await writer.drain()

        if self._stop_forever:
            return False

        received_handshake = await receive_handshake(reader, self._stats)

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


async def open_connection(host: str, port: int) -> [asyncio.StreamReader,
                                                    asyncio.StreamWriter]:
    """
    A wrapper for asyncio.open_connection() returning a (reader, writer) pair.

    :param host: hostname of the peer
    :param port: port to connect to

    :returns: `StreamReader` and `StreamWriter` instances to read and send messages.
    """
    loop = asyncio.events.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(
        lambda: protocol, host, port)
    transport.set_write_buffer_limits(0)  # let the OS handle buffering
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer


async def close_connection(writer: asyncio.StreamWriter):
    """
    Closes the `StreamWriter`

    :param writer: the `StreamWriter` to close.
    """
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def receive_handshake(reader: asyncio.StreamReader,
                            stats: PeerConnectionStats = None) -> Optional[Handshake]:
    """
    Receives and decodes the handshake message sent by the peer.

    :param reader: `asyncio.StreamReader` to read handshake from.
    :param stats: `PeerConnectionStats` to populate data into.

    :return: Decoded `Handshake` if successfully read, otherwise None.
    :raises `PeerError`: if disconnected.
    """
    assert reader is not None

    if reader.at_eof() or reader.exception():
        raise PeerError("Cannot receive message on disconnected reader.")

    data = await reader.readexactly(Handshake.msg_len)
    if stats:
        stats.bytes_downloaded += Handshake.msg_len
    return Handshake.decode(data)


async def read_messages_task(reader: asyncio.StreamReader,
                             received_msg_queue: asyncio.Queue,
                             download_stats: PeerConnectionStats = None):
    """
    Coroutine intended to be scheduled as a task that will continually
    read messages from the peer and populate them into the given queue.

    :param reader: `StreamReader` to read from.
    :param received_msg_queue: `Queue` to place messages into.
    :param download_stats: Optional `PeerConnectionStatus` object to populate stats into.
    """
    while True:
        received = await _receive_from_peer(reader, download_stats)
        if received:
            asyncio.create_task(received_msg_queue.put(received))


async def _receive_from_peer(reader: asyncio.StreamReader,
                             stats: PeerConnectionStats) -> ProtocolMessage:
    """
    Receives and decodes the next message sent by the peer.

    :param reader: `StreamReader` to read from.
    :param stats: `PeerConnectionStats` to update.

    :return: The specific instance of the `ProtocolMessage` received.
    :raises `PeerError`: on exception or if disconnected.
    """
    assert reader is not None

    if reader.at_eof() or reader.exception():
        raise PeerError("Cannot receive message on disconnected reader.")

    try:
        msg_len = struct.unpack(">I", await reader.readexactly(4))[0]
        stats.bytes_downloaded += 4

        if msg_len == 0:
            return KeepAlive()

        msg_id = struct.unpack(">B", await reader.readexactly(1))[0]
        if msg_id is None or (not (0 <= msg_id <= 8)):
            raise PeerError("Unknown message received: %s" % msg_id)

        # the msg_len includes 1 byte for the id
        msg_len -= 1
        if msg_len == 0:
            return MESSAGE_TYPES[msg_id].decode()

        msg_data = await reader.readexactly(msg_len)
        if stats:
            stats.bytes_downloaded += msg_len

        return MESSAGE_TYPES[msg_id].decode(msg_data)
    except Exception as e:
        raise PeerError from e
