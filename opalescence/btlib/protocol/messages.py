#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import logging
import struct
from asyncio import Queue, CancelledError
from typing import Optional

import bitstring as bitstring

logger = logging.getLogger(__name__)


class MessageReaderException(Exception):
    """
    Raised when there's an error with the MessageReader.
    """

    def __init__(self, failure_reason: Optional[str]):
        self.failure_reason = failure_reason


class Message:
    """
    Base class for representing messages exchanged with the protocol

    Messages (except the initial handshake) look like:
    <Length prefix><Message ID><Payload>
    """

    def __str__(self):
        return str(type(self).__name__)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return type(self) == type(other)


class Handshake(Message):
    """
    Handles the handshake message with the protocol
    """
    msg_len = 68
    fmt = struct.Struct(">B19s8x20s20s")

    def __init__(self, info_hash: bytes, peer_id: bytes):
        self.info_hash = info_hash
        self.peer_id = peer_id

    def __eq__(self, other):
        return self.info_hash == other.info_hash and self.peer_id == other.peer_id

    def __str__(self):
        return f"Handshake: {self.peer_id}:{self.info_hash}"

    def encode(self) -> bytes:
        """
        :return: handshake data to send to protocol
        """
        return self.fmt.pack(19, b'BitTorrent protocol',
                             self.info_hash, self.peer_id)

    @classmethod
    def decode(cls, handshake_data: bytes) -> Handshake:
        """
        :return: Handshake instance
        """
        unpacked_data = cls.fmt.unpack(handshake_data)
        return cls(unpacked_data[2], unpacked_data[3])


class KeepAlive(Message):
    """
    keep alive message

    <0000>
    """

    @staticmethod
    def encode() -> bytes:
        """
        :return: encoded message to be sent to protocol
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
        :return: encoded message to be sent to protocol
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
        :return: encoded message to be sent to protocol
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
        :return: encoded message to be sent to protocol
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
        :return: encoded message to be sent to protocol
        """
        return struct.pack(">IB", 1, NotInterested.msg_id)


class Have(Message):
    """
    have message

    <0005><4><index>
    """
    msg_id = 4

    def __init__(self, index: int):
        self.index = index

    def __eq__(self, other):
        return self.index == other.index

    def __str__(self):
        return f"Have: {self.index}"

    def encode(self) -> bytes:
        """
        :return: encoded message to be sent to protocol
        """
        return struct.pack(">IBI", 5, self.msg_id, self.index)

    @classmethod
    def decode(cls, data: bytes) -> Have:
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

    def __init__(self, bitfield: bytes):
        self.bitfield = bitstring.BitArray(bytes=bitfield)

    def __eq__(self, other):
        return self.bitfield == other.bitfield

    def __str__(self):
        return f"Bitfield: {self.bitfield}"

    def encode(self) -> bytes:
        """
        :return: encoded message to be sent to protocol
        """
        bitfield_len = len(self.bitfield)
        return struct.pack(f">IB{bitfield_len}s", 1 + bitfield_len,
                           Bitfield.msg_id, self.bitfield)

    @classmethod
    def decode(cls, data: bytes) -> Bitfield:
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

    def __init__(self, index: int, begin: int, length: int = size, peer_id: str = ""):
        self.index = index
        self.begin = begin
        self.length = length
        self.peer_id = peer_id

    def __eq__(self, other):
        return self.index == other.index and self.begin == other.begin

    def __str__(self):
        return f"Request: {self.index}:{self.begin}:{self.length}"

    def encode(self) -> bytes:
        """
        :return: the request message encoded in bytes
        """
        return struct.pack(">IB3I", 13, self.msg_id, self.index, self.begin,
                           self.length)

    @classmethod
    def decode(cls, data: bytes) -> Request:
        """
        :return: a decoded request message
        """
        request = struct.unpack(">3I", data)
        return cls(request[0], request[1], request[2])


class Block(Message):
    """
    block message

    <0009+X><7><index><begin><block>
    """
    msg_id = 7

    def __init__(self, index: int, begin: int, data: bytes):
        self.index = index  # index of the actual piece
        self.begin = begin  # offset into the piece
        self.data = data
        if len(self.data) != Request.size:
            logger.debug(f"Piece {self} received with a weird size: {len(self.data)}.")

    def __eq__(self, other):
        return self.index == other.index and self.begin == other.begin and self.data == other.data

    def __str__(self):
        return f"Block: {self.index}:{self.begin}:{self.data}"

    def encode(self) -> bytes:
        """
        :return: the piece message encoded in bytes
        """
        data_len = len(self.data)
        return struct.pack(f">IBII{data_len}s", 9 + data_len, Block.msg_id,
                           self.index, self.begin, self.data)

    @classmethod
    def decode(cls, data: bytes) -> Block:
        """
        :return: a decoded piece message
        """
        data_len = len(data) - 8  # account for the index and begin bytes
        piece_data = struct.unpack(f">II{data_len}s", data)
        return cls(piece_data[0], piece_data[1], piece_data[2])


class Piece:
    """
    Represents a piece of the torrent.
    Pieces are made up of blocks.

    Not really a message itself
    """

    def __init__(self, index, length):
        self.index: int = index
        self.length: int = length
        self.data: bytes = b''

    def __eq__(self, other: Piece):
        return self.index == other.index \
               and self.data == other.data \
               and self.length == other.length

    def __str__(self):
        return f"Piece ({self.index}:{self.length}): {self.data}"

    def add_block(self, block: Block):
        """
        Adds a block to this piece.
        :param block: The block message containing the block's info
        """
        assert (self.index == block.index)
        if block.begin != len(self.data):
            logger.debug(f"Block begin index is non-sequential for: {self}\n{block}")
            return
        self.data += block.data

    @property
    def complete(self) -> bool:
        """
        :return: True if all blocks have been downloaded
        """
        return len(self.data) == self.length

    @property
    def next_block(self) -> Optional[int]:
        """
        :return: The offset of the next block, or None if there are no blocks left.
        """
        if self.complete:
            return
        return len(self.data)

    def reset(self):
        """
        Resets the piece leaving it in a state equivalent to immediately after initializing.
        Used when we've downloaded the piece, but it turned out to be corrupt.
        """
        self.data = b''


class Cancel(Message):
    """
    cancel message

    <0013><8><index><begin><length>
    """
    msg_id = 8
    size = 2 ** 14

    def __init__(self, index: int, begin: int, length: int = size):
        self.index = index
        self.begin = begin
        self.length = length

    def __eq__(self, other):
        return self.index == other.index and self.begin == other.begin and self.length == other.length

    def __str__(self):
        return f"Cancel: {self.index}:{self.begin}:{self.length}"

    def encode(self) -> bytes:
        """
        :return: the cancel message encoded in bytes
        """
        return struct.pack(">IBIII", 13, Cancel.msg_id, self.index, self.begin, self.length)

    @classmethod
    def from_request(cls, request: Request) -> Cancel:
        """
        :param request: Request message we want to cancel.
        :return: A Cancel message from a request
        """
        return cls(request.index, request.begin, request.length)

    @classmethod
    def decode(cls, data: bytes) -> Cancel:
        """
        :return: a decoded cancel message
        """
        cancel_data = struct.unpack(">III", data)
        return cls(cancel_data[0], cancel_data[1], cancel_data[2])


class MessageReader:
    """
    Asynchronously reads the data sent by the remote peer and decodes
    it into the appropriate protocol message. This message is added
    to the shared queue where it can be picked up and worked later.
    """

    CHUNK_SIZE = 10 * 1024

    def __init__(self, reader: asyncio.StreamReader, msg_queue: Queue):
        self._data = bytearray()
        self._reader = reader
        self._task: Optional[asyncio.Task] = None
        self._queue = msg_queue

    def start(self) -> asyncio.Task:
        """
        Schedules and returns the task that continually reads from the StreamReader and consumes messages.
        :return: The asyncio.Task for self._parse()
        """
        logger.debug("Starting MessageReader")
        self._task = asyncio.create_task(self._parse())
        return self._task

    def stop(self) -> bool:
        """
        :return: True if the message reader task has been successfully cancelled.
        """
        logger.debug("Stopping MessageReader")
        return self._task.cancel()

    async def _consume(self, num: int) -> bytes:
        """
        Consumes and returns the specified number of bytes from the buffer.

        :param num: number of bytes to consume
        :raises MessageReaderException:
        :return: bytes consumed from the buffer
        """
        while len(self._data) < num:
            data = await self._reader.read(self.CHUNK_SIZE)
            if data:
                self._data += data
            else:
                logger.debug(f"Couldn't read at least {self.CHUNK_SIZE} bytes from the stream.")
                raise MessageReaderException("Unable to read data from stream...")

        read_bytes = self._data[:num]
        self._data = self._data[num:]
        return read_bytes

    async def _parse(self):
        """
        Iterates through the data we have, requesting more
        from the protocol if necessary, and tries to decode and add
        a valid message from that data to a queue

        :raises MessageReaderException:
        """
        try:
            while True:
                msg_len = struct.unpack(">I", await self._consume(4))[0]

                if msg_len == 0:
                    self._queue.put_nowait(KeepAlive())
                    continue

                msg_id = struct.unpack(">B", await self._consume(1))[0]
                msg_len -= 1  # the msg_len includes 1 byte for the id, we've consumed that already

                if msg_id == 0:
                    await self._queue.put(Choke())
                elif msg_id == 1:
                    await self._queue.put(Unchoke())
                elif msg_id == 2:
                    await self._queue.put(Interested())
                elif msg_id == 3:
                    await self._queue.put(NotInterested())
                elif msg_id == 4:
                    await self._queue.put(Have.decode(await self._consume(msg_len)))
                elif msg_id == 5:
                    await self._queue.put(Bitfield.decode(await self._consume(msg_len)))
                elif msg_id == 6:
                    await self._queue.put(Request.decode(await self._consume(msg_len)))
                elif msg_id == 7:
                    await self._queue.put(Block.decode(await self._consume(msg_len)))
                elif msg_id == 8:
                    await self._queue.put(Cancel.decode(await self._consume(msg_len)))
                else:
                    raise MessageReaderException(f"Unexpected message ID received: {msg_id}")
        except MessageReaderException as mre:
            raise mre
        except CancelledError as ce:
            logger.debug("Cancelling MessageReader task & shutting down...")
            raise ce
