# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now
"""

import asyncio
import logging
import struct

PSTR = "BitTorrent protocol"
PSTRLEN = 19

logger = logging.getLogger('opalescence.' + __name__)


class Messages(object):
    keep_alive = struct.pack("!i", 0)
    choke = struct.pack("!i", 1) + struct.pack("!b", 0)
    unchoke = struct.pack("!i", 1) + struct.pack("!b", 1)
    interested = struct.pack("!i", 1) + struct.pack("!b", 2)
    not_interested = struct.pack("!i", 1) + struct.pack("!b", 3)


class Peer:
    """
    Represents a peer and provides methods for communicating with said peer.
    """
    _handshake_len = 68

    def __init__(self, ip, port, info_hash, peer_id):
        self.ip = ip
        self.port = port
        self.info_hash = info_hash
        self.peer_id = peer_id
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
        while True:
            try:
                self.reader, self.writer = await asyncio.open_connection(host=self.ip, port=self.port)
                logger.debug(f"Opened connection with peer: {self.ip}:{self.port}")

                buffer = await self._handshake()
            except OSError:
                logger.debug("Unable to open connection to {peer}".format(peer=self))
                raise

    async def _handshake(self):
        logger.debug("Initiating handshake with peer {peer}".format(peer=self))
        msg = struct.pack('>B19s8x20s20s', 19, b'BitTorrent protocol', self.info_hash, self.peer_id)
        self.writer.write(msg)
        await self.writer.drain()

        buf = b''
        logger.debug("receiving handshake data")
        while len(buf) < self._handshake_len:
            buf = await self.reader.read(10 * 1024)

        resp = self._parse_msg(buf[:self._handshake_len])
        logger.debug(f"decoded message from peer {resp}")
        return resp

    def _parse_msg(self, message: bytes) -> tuple:
        return struct.unpack('>B19s8x20s20s', message)
