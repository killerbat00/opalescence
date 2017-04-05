# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now
"""
import asyncio
import logging
import struct

from . import log_and_raise

logger = logging.getLogger(__name__)


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """
    pass


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

    async def parse_msg(self):
        """
        Parses a message from the data buffer, requesting more from the reader, if necessary, consumes it,
        and returns it to be handled
        :return: Message instance describing message
        """
        if not self.data_buffer or len(self.data_buffer) < 4:
            try:
                self.data_buffer += await self.reader.read(10 * 1024)

                msg_len = struct.unpack(">I", self.data_buffer[:4])[0]
                self.data_buffer = self.data_buffer[4:]

                # keep alive
                if msg_len == 0:
                    logger.debug(f"{self}: Sent keep-alive message.")

                msg_id = struct.unpack(">B", self.data_buffer[:1])[0]
                self.data_buffer = self.data_buffer[1:]

                if msg_id == 0:
                    logger.debug(f"{self}: sent choke message.")
                    self.peer_choking = True
                elif msg_id == 1:
                    logger.debug(f"{self}: sent unchoke message.")
                    self.peer_choking = False
                elif msg_id == 2:
                    logger.debug(f"{self}: sent interested message.")
                    self.peer_interested = True
                elif msg_id == 3:
                    logger.debug(f"{self}: sent not interested message.")
                    self.peer_interested = False
                elif msg_id == 4:
                    logger.debug(f"{self}: sent have message.")

                    while len(self.data_buffer) < msg_len - 1:
                        self.data_buffer += await self.reader.read(10 * 1024)

                    piece = struct.unpack(">I", self.data_buffer[:msg_len - 1])
                    logger.debug(f"{self}: has piece {piece}")
                    self.data_buffer = self.data_buffer[msg_len - 1:]
                elif msg_id == 5:
                    logger.debug(f"{self}: sent bitfield message.")

                    while len(self.data_buffer) < msg_len - 1:
                        self.data_buffer += await self.reader.read(10 * 1024)

                    bitfield = self.data_buffer[:msg_len - 1]
                    logger.debug(f"{self}: sent bitfield {bitfield}")
                    self.data_buffer = self.data_buffer[msg_len - 1:]
                elif msg_id == 6:
                    logger.debug(f"{self}: sent request message.")

                    while len(self.data_buffer) < msg_len - 1:
                        self.data_buffer += await self.reader.read(10 * 1024)

                    request = struct.unpack(">3I", self.data_buffer[:msg_len - 1])
                    logger.debug(f"{self}: requested block {request}")
                    self.data_buffer = self.data_buffer[msg_len - 1:]
                elif msg_id == 7:
                    logger.debug(f"{self}: sent piece (block) message.")
                    block_len = msg_len - 9

                    while len(self.data_buffer) < msg_len - 1:
                        self.data_buffer += await self.reader.read(10 * 1024)

                    block = struct.unpack(f">2I{block_len}s", self.data_buffer[:msg_len - 1])
                    logger.debug(f"{self}: sent block {block}")
                    self.data_buffer = self.data_buffer[msg_len - 1:]
                elif msg_id == 8:
                    logger.debug(f"{self}: sent cancel message.")
                    while len(self.data_buffer) < msg_len - 1:
                        self.data_buffer += await self.reader.read(10 * 1024)

                    canceled = struct.unpack(">31", self.data_buffer[:msg_len - 1])
                    logger.debug(f"{self}: cancelled request {canceled}")
                    self.data_buffer = self.data_buffer[msg_len - 1:]

            except (ConnectionResetError, Exception) as e:
                log_and_raise(f"{self}: Unable to read message.", logger, PeerError, e)

    async def _start(self):
        # TODO: scan valid bittorrent ports (6881-6889) if we can't connect on the first port
        try:
            self.reader, self.writer = await asyncio.open_connection(host=self.ip, port=self.port)
            logger.debug(f"{self}: Opened peer connection")
            self.data_buffer = await self.handshake()
            # deal with leftover bytes we've read from the stream after negotiating the handshake

            while self.alive:
                await self.parse_msg()

        except (OSError, PeerError, ConnectionResetError, ConnectionRefusedError) as e:
            logger.debug("Unable to open connection to {peer}".format(peer=self))
            raise PeerError from e

    async def handshake(self) -> bytes:
        """
        Negotiates the initial handshake with the peer.

        :raises PeerError:
        :return: remaining data we've read from the reader
        """
        # TODO: validate the peer id we receive is the same as from the tracker if we got a dictionary style response
        logger.debug(f"{self} Initiating handshake")
        sent_handshake = Handshake(self.info_hash, self.id)
        self.writer.write(sent_handshake.encode())
        await self.writer.drain()

        data = b''
        while len(data) < Handshake.msg_len:
            data = await self.reader.read(10 * 1024)
            if not data:
                log_and_raise(f"{self}: Unable to initiate handshake", logger, PeerError)

        rcvd_handshake = Handshake.decode(data[:Handshake.msg_len])
        logger.debug(f"Decoded message from peer {rcvd_handshake}")

        if rcvd_handshake.info_hash != self.info_hash:
            log_and_raise(f"{self}: Incorrect info hash received {rcvd_handshake.info_hash}", logger, PeerError)

        return data[Handshake.msg_len:]


class Handshake:
    """
    Represents the handshake message negotiated with a peer.
    """
    msg_len = 68

    def __init__(self, info_hash: bytes, peer_id: bytes):
        self.info_hash = info_hash
        self.peer_id = peer_id

    def encode(self) -> bytes:
        """
        Packs the handshake message into raw bytes.

        :return:          raw handshake data to send to peer
        """
        return struct.pack(">B19s8x20s20s", 19, b'BitTorrent protocol', self.info_hash, self.peer_id)

    @classmethod
    def decode(cls, handshake_data: bytes) -> "Handshake":
        """
        Decodes data received from the peer after we send them the handshake.

        :param handshake_data: data to unpack from handshake exchange
        :return: "Handshake" instance
        """
        unpacked_data = struct.unpack(">B19s8x20s20s", handshake_data)
        return cls(unpacked_data[2], unpacked_data[3])
