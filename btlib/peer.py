# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now


author: brian houston morrow

TODO: connections to multiple peers
"""

import asyncio
import logging
import socket
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


class Peer(object):
    """
    Represents a peer and provides methods for communicating with said peer.
    """
    _reserved = struct.pack("!q", 0)
    _handshake_len = 68
    _pstr_len_bytes = struct.pack("!B", PSTRLEN)

    def __init__(self, ip: int, port: int, info_hash: str, peer_id):
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
        logger.debug("Initiating handshake with peer {ip}:{port}".format(ip=self.ip, port=self.port))
        msg = "{pstrlen}{pstr}{reserved}{info_hash}{peer_id}".format(pstrlen=self._pstr_len_bytes, pstr=PSTR,
                                                                     reserved=self._reserved, info_hash=self.info_hash,
                                                                     peer_id=self.peer_id).encode("ISO-8859-1")

        loop = asyncio.get_event_loop()
        try:
            reader, writer = await asyncio.open_connection(host=self.ip, port=self.port, loop=loop)
        except OSError as oe:
            logger.debug("Unable to open connection to {peer}".format(peer=self))
            raise socket.error from oe

        try:
            writer.write(msg)
            await writer.drain()
            # why is msg blank here when returning from await?
            logger.debug("[*] Sent message {message}".format(message=msg.decode("ISO-8859-1")))
            e = reader.exception()
            if e:
                raise socket.error from e
        except:
            logger.debug("Error writing to {peer}".format(peer=self))
            raise socket.error

        try:
            chunks = await reader.read()
            if chunks == 0:
                logger.debug("No data received")
                raise socket.error
        except:
            logger.debug("Error reading from {peer}".format(peer=self))
            raise socket.error

        handshake_resp = chunks.decode("ISO-8859-1")
        logger.debug("[*] Received message {message}".format(message=handshake_resp))
        return

    def _parse_msg(self, message):
        # assert (len(message) == self._handshake_len)

        print(message)
        print("halt")
