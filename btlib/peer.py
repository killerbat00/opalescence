# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now


author: brian houston morrow

TODO: connections to multiple peers
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
        self.future = asyncio.ensure_future(self._start())

    def __str__(self):
        return "{ip}:{port}".format(ip=self.ip, port=self.port)

    async def _start(self):
        while True:
            logger.debug("Initiating handshake with peer {peer}".format(peer=self))

            try:
                self.reader, self.writer = await asyncio.open_connection(host=self.ip, port=self.port)
                logger.debug("Opened connection with peer: {ip:port}".format(ip=self.ip, port=self.port))

                buffer = await self._handshake()
                print(buffer)
            except OSError:
                logger.debug("Unable to open connection to {peer}".format(peer=self))
                return

    async def _handshake(self):
        msg = struct.pack('>B19s8x20s20s', 19, b'BitTorrent protocol', '', self.info_hash, self.peer_id)
        # construct message
        self.writer.write(msg)
        await self.writer.drain()

        buf = b''
        while len(buf) < self._handshake_len:
            buf = await self.reader.read()
            print(buf)
            self._parse_msg(buf, msg)
            # decode response

        #        except:
        #            logger.debug("Error writing to {peer}".format(peer=self))
        #            return
        #        try:
        #            chunks = await reader.read()
        #            if not chunks:
        #                logger.debug("No data received")
        #                return
        #        except:
        #            logger.debug("Error reading from {peer}".format(peer=self))
        #            return
        #        msg = "{pstrlen}{pstr}{reserved}{info_hash}{peer_id}".format(pstrlen=self._pstr_len_bytes, pstr=PSTR,
        #                                                                     reserved=self._reserved, info_hash=self.info_hash,
        #                                                                     peer_id=self.peer_id).encode("ISO-8859-1")
        #        message = "%s%s%s%s%s" % (chr(19), "BitTorrent protocol", 8 * chr(0),
        #                                  self.info_hash, self.peer_id)
        #        message = message.encode("ISO-8859-1")
        #
        #        loop = asyncio.get_event_loop()
        #
        #        print(chunks)
        #        self._parse_msg(chunks, msg)
        #        logger.debug("[*] Received message {message}".format(message=chunks.decode("ISO-8859-1")))

    def _parse_msg(self, message: bytes, orig: bytes):
        parts = struct.unpack('>B19s8x20s20s', message[:68])
        print(struct.unpack("B" * len(message), message))
        a = message[:1]
        b = message[1:69]
        #        print(orig)
        #        print(a)
        #        print(b)

        #        message = BytesIO(message)
        #        print(binascii.hexlify(message))
        #        msg_len = int.from_bytes(message.read(1), byteorder='big')
        #        other_pstrlen = int.from_bytes(message.read(1), byteorder='big')
        #        other_pstr = message.read(other_pstrlen)
        #        other_reserved = message.read(8)
        #        other_infohash = message.read(20)
        #        other_peerid = message.read(20)
        #        a = message.read()
        #        a = other_pstr.decode("ISO-8859-1")
        print("hmm")
        return
