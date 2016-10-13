# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now


author: brian houston morrow

TODO: connections to multiple peers
"""

import asyncio
import binascii
import logging
import struct
from io import BytesIO

PSTR = "BitTorrent protocol"
PSTRLEN = 19

logger = logging.getLogger('opalescence.' + __name__)


class Messages(object):
    keep_alive = struct.pack("!i", 0)
    choke = struct.pack("!i", 1) + struct.pack("!b", 0)
    unchoke = struct.pack("!i", 1) + struct.pack("!b", 1)
    interested = struct.pack("!i", 1) + struct.pack("!b", 2)
    not_interested = struct.pack("!i", 1) + struct.pack("!b", 3)


class Peer(object):
    """
    Represents a peer and provides methods for communicating with said peer.
    """
    _reserved = struct.pack("!q", 0)
    _handshake_len = 68
    _pstr_len_bytes = struct.pack("!B", PSTRLEN)

    def __init__(self, ip: int, port: int, info_hash: str, peer_id, ):
        self.ip = ip
        self.port = port
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.am_choking = True
        self.am_interested = False
        self.peer_choking = True
        self.peer_interested = False

    def __str__(self):
        return "{ip}:{port}".format(ip=self.ip, port=self.port)

    async def basic_comm(self):
        logger.debug("Initiating handshake with peer {peer}".format(peer=self))
        msg = "{pstrlen}{pstr}{reserved}{info_hash}{peer_id}".format(pstrlen=self._pstr_len_bytes, pstr=PSTR,
                                                                     reserved=self._reserved, info_hash=self.info_hash,
                                                                     peer_id=self.peer_id).encode("ISO-8859-1")

        loop = asyncio.get_event_loop()
        try:
            reader, writer = await asyncio.open_connection(host=self.ip, port=self.port, loop=loop)
        except OSError:
            logger.debug("Unable to open connection to {peer}".format(peer=self))
            return

        try:
            writer.write(msg)
            await writer.drain()
            logger.debug("[*] Sent message {message}".format(message=msg.decode("ISO-8859-1")))

        except:
            logger.debug("Error writing to {peer}".format(peer=self))
            return
        try:
            chunks = await reader.read()
            if not chunks:
                logger.debug("No data received")
                return
        except:
            logger.debug("Error reading from {peer}".format(peer=self))
            return

        print(chunks)
        self._parse_msg(chunks)
        logger.debug("[*] Received message {message}".format(message=chunks.decode("ISO-8859-1")))

    def _parse_msg(self, message: bytes):
        message = BytesIO(message)
        print(binascii.hexlify(message))
        msg_len = int.from_bytes(message.read(1), byteorder='big')
        other_pstrlen = int.from_bytes(message.read(1), byteorder='big')
        other_pstr = message.read(other_pstrlen)
        other_reserved = message.read(8)
        other_infohash = message.read(20)
        other_peerid = message.read(20)
        a = message.read()
        a = other_pstr.decode("ISO-8859-1")
        print("hmm")
        return
