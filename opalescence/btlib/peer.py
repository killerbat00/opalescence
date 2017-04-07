# -*- coding: utf-8 -*-

"""
Support for basic communication with a peer.
The piece-requesting strategy is naive at the moment. We request pieces (and blocks) starting at index 0.
No data is currently written to disk or sent.
"""
import asyncio
import logging
import struct

import bitstring as bitstring

from . import log_and_raise

logger = logging.getLogger(__name__)


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """


class Message:
    """
    Base class for representing messages exchanged with the peer

    Messages (except the initial handshake) look like:
    <Length prefix><Message ID><Payload>
    """
    def __str__(self):
        return str(type(self))


class Handshake(Message):
    """
    Handles the handshake message with the peer
    """
    msg_len = 68

    def __init__(self, info_hash: bytes, peer_id: bytes):
        self.info_hash = info_hash
        self.peer_id = peer_id

    def __str__(self):
        return f"{self.info_hash}:{self.peer_id}"

    def encode(self) -> bytes:
        """
        :return: handshake data to send to peer
        """
        return struct.pack(">B19s8x20s20s", 19, b'BitTorrent protocol',
                           self.info_hash, self.peer_id)

    @classmethod
    def decode(cls, handshake_data: bytes) -> "Handshake":
        """
        :return: Handshake instance
        """
        unpacked_data = struct.unpack(">B19s8x20s20s", handshake_data)
        return cls(unpacked_data[2], unpacked_data[3])


class KeepAlive(Message):
    """
    keep alive message

    <0000>
    """

    @staticmethod
    def encode() -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        return struct.pack(">I", 0)


class Choke(Message):
    """
    choke message

    <0001><0>
    """
    msg_id = 0

    @staticmethod
    def encode() -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        return struct.pack(">IB", 1, Choke.msg_id)


class Unchoke(Message):
    """
    unchoke message

    <0001><1>
    """
    msg_id = 1

    @staticmethod
    def encode() -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        return struct.pack(">IB", 1, Unchoke.msg_id)


class Interested(Message):
    """
    interested message

    <0001><2>
    """
    msg_id = 2

    @staticmethod
    def encode() -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        return struct.pack(">IB", 1, Interested.msg_id)


class NotInterested(Message):
    """
    not interested message

    <0001><3>
    """
    msg_id = 3

    @staticmethod
    def encode() -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        return struct.pack(">IB", 1, NotInterested.msg_id)


class Have(Message):
    """
    have message

    <0005><4><index>
    """
    msg_id = 4

    def __str__(self):
        return f"{self.index}"

    def __init__(self, index: int):
        self.index = index

    def encode(self) -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        return struct.pack(">IBI", 5, self.msg_id, self.index)

    @classmethod
    def decode(cls, data: bytes) -> "Have":
        """
        :return: an instance of the have message
        """
        piece = struct.unpack(">I", data)[0]
        return cls(piece)


class Bitfield(Message):
    """
    bitfield message

    <0001+X><5><bitfield>
    """
    msg_id = 5

    def __str__(self):
        return f"{self.bitfield}"

    def __init__(self, bitfield: bytes):
        self.bitfield = bitstring.BitArray(bytes=bitfield)

    def encode(self) -> bytes:
        """
        :return: encoded message to be sent to peer
        """
        bitfield_len = len(self.bitfield)
        return struct.pack(f">IB{bitfield_len}s", 1 + bitfield_len,
                           Bitfield.msg_id, self.bitfield)

    @classmethod
    def decode(cls, data: bytes) -> "Bitfield":
        """
        :return: an instance of the bitfield message
        """
        bitfield = struct.unpack(f">{len(data)}s", data)[0]
        return cls(bitfield)


class Request(Message):
    """
    request message

    <0013><6><index><begin><length>
    """
    msg_id = 6
    size = 2 ** 14

    def __str__(self):
        return f"{self.index}:{self.begin}:{self.length}"

    def __init__(self, index: int, begin: int, length: int=size):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self) -> bytes:
        """
        :return: the request message encoded in bytes
        """
        return struct.pack(">IB3I", 13, self.msg_id, self.index, self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes) -> "Request":
        """
        :return: a decoded request message
        """
        request = struct.unpack(">3I", data)
        return cls(request[0], request[1], request[2])


class Piece(Message):
    """
    piece message

    <0009+X><7><index><begin><block>
    """
    msg_id = 7

    def __str__(self):
        return f"{self.index}:{self.begin}:{self.data}"

    def __init__(self, index: int, begin: int, data: bytes):
        self.index = index
        self.begin = begin
        self.data = data

    def encode(self) -> bytes:
        """
        :return: the piece message encoded in bytes
        """
        data_len = len(self.data)
        return struct.pack(f">IBII{data_len}s", 9 + data_len, Piece.msg_id,
                           self.index, self.begin, self.data)

    @classmethod
    def decode(cls, data: bytes) -> "Piece":
        """
        :return: a decoded piece message
        """
        data_len = len(data)
        piece_data = struct.unpack(f">II{data_len}s", data)
        return cls(piece_data[0], piece_data[1], piece_data[2])


class Cancel(Message):
    """
    cancel message

    <0013><8><index><begin><length>
    """
    msg_id = 8
    size = 2 ** 14

    def __str__(self):
        return f"{self.index}:{self.begin}:{self.length}"

    def __init__(self, index: int, begin: int, length: int=size):
        self.index = index
        self.begin = begin
        self.length = length

    def encode(self) -> bytes:
        """
        :return: the cancel message encoded in bytes
        """
        return struct.pack(">IBIII", 13, Cancel.msg_id, self.index, self.begin, self.length)

    @classmethod
    def decode(cls, data: bytes) -> "Cancel":
        """
        :return: a decoded cancel message
        """
        cancel_data = struct.unpack(">III", data)
        return cls(cancel_data[0], cancel_data[1], cancel_data[2])


class MessageReader:
    """
    Asynchronously reads a message from a StreamReader and tries to
    parse valid BitTorrent protocol messages from the data consumed.
    """
    CHUNK_SIZE = 10 * 1024

    def __init__(self, reader: asyncio.StreamReader, data: bytes):
        self.data_buffer = data
        self.reader = reader

    async def _fetch(self) -> bytes:
        """
        Fetches data from the StreamReader.
        Raises exception if no data is returned.

        :raises StopAsyncIteration:
        :return: data from the StreamReader
        """
        data = await self.reader.read(self.CHUNK_SIZE)
        if not data:
            raise StopAsyncIteration()
        return data

    async def _consume(self, num: int) -> bytes:
        """
        Consumes and returns the specified number of bytes from the buffer.

        :param num: number of bytes to consume
        :return: bytes consumed from the buffer
        """
        while len(self.data_buffer) < num:
            self.data_buffer += await self._fetch()

        consumed = self.data_buffer[:num]
        self.data_buffer = self.data_buffer[num:]
        return consumed

    async def __aiter__(self):
        return self

    async def __anext__(self) -> Message:
        """
        Iterates through the data we have, requesting more
        from the peer if necessary, and tries to decode and return
        a valid message from that data.

        :raises StopAsyncIteration:
        :return: instance of the message that was received
        """
        msg_len = struct.unpack(">I", await self._consume(4))[0]

        if msg_len == 0:
            return KeepAlive()

        msg_id = struct.unpack(">B", await self._consume(1))[0]

        if msg_id == 0:
            return Choke()
        elif msg_id == 1:
            return Unchoke()
        elif msg_id == 2:
            return Interested()
        elif msg_id == 3:
            return NotInterested()
        elif msg_id == 4:
            have_index = await self._consume(msg_len - 1)
            return Have.decode(have_index[1:])
        elif msg_id == 5:
            bitfield = await self._consume(msg_len - 1)
            return Bitfield.decode(bitfield[1:])
        elif msg_id == 6:
            request = await self._consume(msg_len - 1)
            return Request.decode(request[1:])
        elif msg_id == 7:
            piece = await self._consume(msg_len - 1)
            return Piece.decode(piece[1:])
        elif msg_id == 8:
            cancel = await self._consume(msg_len - 1)
            return Cancel.decode(cancel[1:])
        else:
            raise StopAsyncIteration()


class Peer:
    """
    Represents a peer and provides methods for communicating with said peer.
    """

    def __init__(self, ip, port, info_hash, peer_id):
        self.ip = ip
        self.port = port
        self.info_hash = info_hash
        self.id = peer_id
        self.peer_id = None
        self.reader = None
        self.writer = None
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False
        self.alive = True
        self.data_buffer = b''
        # self.future = asyncio.ensure_future(self._start())

    def __str__(self):
        return f"{self.ip}:{self.port}"

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
            data = await self.reader.read(10 * 1024)
            if not data:
                log_and_raise(f"{self}: Unable to initiate handshake", logger,
                              PeerError)

        rcvd = Handshake.decode(data[:Handshake.msg_len])

        if rcvd.info_hash != self.info_hash:
            log_and_raise(f"{self}: Incorrect info hash received.", logger,
                          PeerError)

        logger.debug(f"{self}: Successfully negotiated handshake.")
        return data[Handshake.msg_len:]

    async def interested(self):
        """
        Sends the interested message to the peer.
        The peer should unchoke us after this.
        """
        self.writer.write(Interested.encode())
        await self.writer.drain()
        self.am_interested = True
        logger.debug(f"Sent interested message to {self}")

    async def _start(self):
        # TODO: scan valid bittorrent ports (6881-6889)
        try:
            self.reader, self.writer = await asyncio.open_connection(
                host=self.ip, port=self.port)

            logger.debug(f"{self}: Opened connection.")
            data = await self.handshake()

            await self.interested()

            while self.alive:
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
                        logger.debug(f"{self}: Has {msg}")
                    elif isinstance(msg, Bitfield):
                        logger.debug(f"{self}: Bitfield {msg}")
                    elif isinstance(msg, Request):
                        logger.debug(f"{self}: Requested {msg}")
                    elif isinstance(msg, Piece):
                        logger.debug(f"{self}: Piece {msg}")
                    elif isinstance(msg, Cancel):
                        logger.debug(f"{self}: Canceled {msg}")
                    else:
                        raise PeerError("Unsupported message type.")

                    if not self.peer_choking and self.am_interested:
                        logger.debug(f"Requesting piece from {self}")

        except Exception as e:
            logger.debug(f"{self}: Unable to open connection.")
            raise PeerError from e

