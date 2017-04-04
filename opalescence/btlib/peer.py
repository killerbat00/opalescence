# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now
"""

import asyncio
import logging
import struct

PSTR = "BitTorrent protocol"
PSTRLEN = 19

logger = logging.getLogger(__name__)


class Messages:
    keep_alive = struct.pack("!i", 0)
    choke = struct.pack("!i", 1) + struct.pack("!b", 0)
    unchoke = struct.pack("!i", 1) + struct.pack("!b", 1)
    interested = struct.pack("!i", 1) + struct.pack("!b", 2)
    not_interested = struct.pack("!i", 1) + struct.pack("!b", 3)


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """
    pass


class Peer:
    """
    Represents a peer and provides methods for communicating with said peer.
    """
    _handshake_len = 68

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
        # self.future = asyncio.ensure_future(self._start())

    def __str__(self):
        return "{ip}:{port}".format(ip=self.ip, port=self.port)

    async def _start(self):
        # while True:
        try:
            self.reader, self.writer = await asyncio.open_connection(host=self.ip, port=self.port)
            logger.debug(f"Opened connection with peer: {self}")
            resp = await self._handshake()

            while True:
                # need at least 4 bytes to decode a message
                if not resp:
                    resp = await self.reader.read(10 * 1024)
                    continue
                if len(resp) < 5:
                    resp = await self.reader.read(10 * 1024)
                else:
                    decoded_resp = struct.unpack(">lB", resp[:5])
                    msg_id = decoded_resp[1]
                    if msg_id == 0:
                        logger.debug(f"Received choke message from {self}.")
                    elif msg_id == 1:
                        logger.debug(f"Received unchoke message from {self}.")
                    elif msg_id == 2:
                        logger.debug(f"Received interested message from {self}.")
                    elif msg_id == 3:
                        logger.debug(f"Received not interested message from {self}.")
                    elif msg_id == 4:
                        logger.debug(f"Received have message from {self}.")
                    elif msg_id == 5:
                        logger.debug(f"Received bitfield message from {self}.")
                        remaining_bytes = len(resp[5:])
                        if len(resp) < decoded_resp[0]:
                            try:
                                bitfield_bytes = resp[5:] + await self.reader.readexactly(
                                    decoded_resp[0] - remaining_bytes)
                                logging.debug(f"Received bitfield from {self}: {bitfield_bytes}")
                                resp = b''
                            except asyncio.IncompleteReadError as ire:
                                logging.debug(f"Couldn't read enough bytes for bitfield. Read bytes {ire.partial}")
                                continue
                        else:
                            bitfield_bytes = resp[5:decoded_resp[0]]
                            logging.debug(f"Received bitfield from {self}: {bitfield_bytes}")
                            resp = resp[decoded_resp[0]:]
                        continue
                    elif msg_id == 6:
                        logger.debug(f"Received request message from {self}.")
                    elif msg_id == 7:
                        logger.debug(f"Received piece message from {self}.")
                    elif msg_id == 8:
                        logger.debug(f"Received cancel message from {self}.")
                continue


        except (OSError, PeerError, ConnectionResetError, ConnectionRefusedError) as e:
            logger.debug("Unable to open connection to {peer}".format(peer=self))
            raise PeerError from e

    async def _handshake(self):
        """
        Negotiates the initial handshake with the peer.

        :return: data leftover in the stream reader
        """
        logger.debug("Initiating handshake with peer {peer}".format(peer=self))
        msg = struct.pack('>B19s8x20s20s', 19, b'BitTorrent protocol', self.info_hash, self.id)
        self.writer.write(msg)
        await self.writer.drain()

        buf = b''
        logger.debug("receiving handshake data")
        while len(buf) < self._handshake_len:
            buf = await self.reader.read(10 * 1024)

        resp = struct.unpack('>B19s8x20s20s', buf[:self._handshake_len])
        logger.debug(f"Decoded message from peer {resp}")

        if resp[2] != self.info_hash:
            logger.error(f"Incorrect info hash received from peer {self} {resp[2]}")
            raise PeerError

        self.peer_id = resp[3]
        if len(buf) > self._handshake_len:
            return buf[self._handshake_len:]
        return
