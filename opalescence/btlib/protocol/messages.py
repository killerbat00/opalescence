# -*- coding: utf-8 -*-

"""
Model classes for messages received over the bittorrent protocol.
"""

from __future__ import annotations

__all__ = ['Message', 'Handshake', 'KeepAlive', 'Choke', 'Unchoke',
           'Interested', 'NotInterested', 'Have', 'Bitfield', 'Request',
           'Block', 'Piece', 'Cancel', 'MESSAGE_TYPES', 'ProtocolMessage']

import hashlib
import struct
from abc import abstractmethod
from typing import Optional, Union, AnyStr

import bitstring

from .errors import NonSequentialBlockError


class Message:
    """
    Base class for messages exchanged with the protocol

    Messages (except the initial handshake) look like:
    <Length prefix><Message ID><Payload>
    """

    def __str__(self):
        return str(type(self).__name__)

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, other):
        return type(self) == type(other)

    @abstractmethod
    def encode(self):
        pass

    @abstractmethod
    def decode(self, *args, **kwargs):
        pass


class NoInfoMessage:
    """
    Base class for a protocol message with only a
    message identifier and no additional info
    """
    msg_id = None

    @classmethod
    def decode(cls):
        return cls()

    @classmethod
    def encode(cls) -> bytes:
        return struct.pack(">IB", 1, cls.msg_id)


class Handshake(Message):
    """
    Handles the handshake message with the protocol
    """
    msg_len = 68
    fmt = struct.Struct(">B19s8x20s20s")

    def __init__(self, info_hash: bytes, peer_id: bytes):
        self.info_hash = info_hash
        self.peer_id = peer_id

    def __str__(self):
        return f"Handshake: ({self.peer_id}:{self.info_hash})"

    def __hash__(self):
        return hash((self.info_hash, self.peer_id))

    def __eq__(self, other: Handshake):
        if not isinstance(other, Handshake):
            return False
        return self.info_hash == other.info_hash and \
               self.peer_id == other.peer_id

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

    @classmethod
    def encode(cls) -> bytes:
        """
        :return: encoded message to be sent to protocol
        """
        return struct.pack(">I", 0)

    @classmethod
    def decode(cls):
        return cls()


class Choke(NoInfoMessage, Message):
    """
    choke message

    <0001><0>
    """
    msg_id = 0


class Unchoke(NoInfoMessage, Message):
    """
    unchoke message

    <0001><1>
    """
    msg_id = 1


class Interested(NoInfoMessage, Message):
    """
    interested message

    <0001><2>
    """
    msg_id = 2


class NotInterested(NoInfoMessage, Message):
    """
    not interested message

    <0001><3>
    """
    msg_id = 3


class Have(Message):
    """
    have message

    <0005><4><index>
    """
    msg_id = 4

    def __init__(self, index: int):
        self.index = index

    def __str__(self):
        return f"Have: {self.index}"

    def __hash__(self):
        return hash(self.index)

    def __eq__(self, other):
        if not isinstance(other, Have):
            return False
        return self.index == other.index

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

    def __init__(self, bitfield: Optional[AnyStr]):
        if isinstance(bitfield, str):
            self.bitfield = bitstring.BitArray("0b" + bitfield)
        elif isinstance(bitfield, bytes):
            self.bitfield = bitstring.BitArray(bytes=bitfield)
        else:
            raise TypeError

    def __str__(self):
        return f"Bitfield: {self.bitfield}"

    def __hash__(self):
        return hash(self.bitfield)

    def __eq__(self, other: Bitfield):
        if not isinstance(other, Bitfield):
            return False
        return self.bitfield == other.bitfield

    def encode(self) -> bytes:
        """
        :return: encoded message to be sent to protocol
        """
        if self.bitfield is None:
            return b''
        bitfield_len = len(self.bitfield)
        return struct.pack(f">IB{bitfield_len}s", 1 + bitfield_len,
                           Bitfield.msg_id, self.bitfield.tobytes())

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

    def __init__(self, index: int, begin: int, length: int = size,
                 peer_id: str = ""):
        self.index = index
        self.begin = begin
        self.length = length
        self.peer_id = peer_id

    def __str__(self):
        return f"Request: ({self.index}:{self.begin}:{self.length})"

    def __hash__(self):
        return hash((self.index, self.begin, self.length))

    def __eq__(self, other: Request):
        if not isinstance(other, Request):
            return False
        return (self.index == other.index and
                self.begin == other.begin and
                self.length == other.length)

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
    size = 2 ** 14

    def __init__(self, index: int, begin: int, data: bytes):
        self.index = index  # index of the actual piece
        self.begin = begin  # offset into the piece
        self.data = data

    def __str__(self):
        return f"Block: ({self.index}:{self.begin}:{len(self.data)})"

    def __hash__(self):
        return hash((self.index, self.begin, len(self.data)))

    def __eq__(self, other: Block):
        if not isinstance(other, Block):
            return False
        return (self.index == other.index and
                self.begin == other.begin and
                self.data == other.data)

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

    Not really a message itself.
    """

    def __init__(self, index, length, mi_length, data=b''):
        self.index: int = index
        self.length: int = length
        self.present: int = len(data)
        self._complete: bool = False
        # the length of pieces as defined in the metainfo file
        self.mi_length: int = mi_length
        self.block_size: int = min(self.mi_length, Block.size)
        self._blocks: list[Block] = []
        self._generate_blocks(data)

    def _generate_blocks(self, data: bytes = b''):
        offset = 0
        while (size := min(self.block_size, self.length - offset)) > 0:
            if data:
                block = Block(self.index, offset, data[offset:offset + size])
            else:
                block = Block(self.index, offset, b'')
            self._blocks.append(block)
            offset += size

    def __str__(self):
        return f"Piece: ({self.index}:{self.length}:{self.remaining})"

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash((self.index, self.length, self.data))

    def __eq__(self, other: Piece):
        if not isinstance(other, Piece):
            return False
        equal = self.index == other.index and self.length and other.length
        if self.complete and other.complete:
            equal &= self.data == other.data
        return equal

    @property
    def data(self) -> bytes:
        return b''.join([b.data for b in self._blocks])

    def add_block(self, block: Block):
        """
        Adds a block to this piece.
        :param block: The block message containing the block's info
        """
        if self.complete:
            return

        assert self.index == block.index

        block_index = block.begin // self.block_size
        if block_index < 0 or block_index > len(self._blocks):
            raise NonSequentialBlockError

        self._blocks[block_index] = block
        self.present += len(block.data)

    def mark_complete(self):
        """
        Marks the piece complete and flushes its data from memory.
        """
        self._complete = True
        self.reset()
        self.present = self.length

    def mark_written(self):
        """
        Marks the piece as written to disk.
        """
        self.mark_complete()

    @property
    def complete(self) -> bool:
        """
        :return: True if all blocks have been bytes_downloaded
        """
        return self._complete or self.present == self.length

    @property
    def remaining(self) -> int:
        """
        :return: The number of bytes remaining in this piece.
        """
        if self.complete:
            return 0
        return self.length - self.present

    def reset(self):
        """
        Resets the piece leaving it in a state equivalent to immediately after
        initializing.
        """
        self.present = 0
        self._generate_blocks()

    def hash(self) -> Optional[bytes]:
        """
        Returns the hash of the piece's data.
        """
        for block in self._blocks:
            if not block.data:
                return
        return hashlib.sha1(self.data).digest()


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

    def __str__(self):
        return f"Cancel: ({self.index}:{self.begin}:{self.length})"

    def __hash__(self):
        return hash((self.index, self.begin, self.length))

    def __eq__(self, other: Cancel):
        if not isinstance(other, Cancel):
            return False
        return (self.index == other.index and
                self.begin == other.begin and
                self.length == other.length)

    def encode(self) -> bytes:
        """
        :return: the cancel message encoded in bytes
        """
        return struct.pack(">IBIII", 13, Cancel.msg_id, self.index, self.begin,
                           self.length)

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


MESSAGE_TYPES = {
    0: Choke,
    1: Unchoke,
    2: Interested,
    3: NotInterested,
    4: Have,
    5: Bitfield,
    6: Request,
    7: Block,
    8: Cancel
}

ProtocolMessage = Union[
    Handshake, KeepAlive, Choke, Unchoke, Interested, NotInterested, Have, Bitfield, Request,
    Block, Cancel]
