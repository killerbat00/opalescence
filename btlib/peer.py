# -*- coding: utf-8 -*-

"""
Support for basic communication with a single peer - for now


author: brian houston morrow

TODO: connections to multiple peers
"""

import socket
import struct

PSTR = "BitTorrent protocol"
PSTRLEN = 19


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

    def handshake(self):
        print(("[*] Initiating handshake with peer {ip}:{port}".format(ip=self.ip, port=self.port)))
        chunks = []
        recvd = 0
        sent = 0
        msg = "{pstrlen}{pstr}{reserved}{info_hash}{peer_id}".format(pstrlen=self._pstr_len_bytes, pstr=PSTR,
                                                                     reserved=self._reserved, info_hash=self.info_hash,
                                                                     peer_id=self.peer_id).encode("ISO-8859-1")

        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.ip, self.port))
        while sent < self._handshake_len:
            i_sent = s.send(msg[sent:])
            if i_sent == 0:
                raise RuntimeError("socket connection broken")
            sent += i_sent
        print(("[*] Sent message".format(message=msg.decode("ISO-8859-1"))))
        while recvd < self._handshake_len:
            chunk = s.recv(self._handshake_len)
            if chunk == '':
                raise RuntimeError("socket connection broken")
            chunks.append(chunk)
            recvd += len(chunk)

        handshake_resp = b"".join(chunks).decode("ISO-8859-1")
        print(("[*] Received message".format(message=handshake_resp)))
        self._parse_msg(handshake_resp)
        print("halt")

    def _parse_msg(self, message):
        assert (len(message) == self._handshake_len)

        print(message)
        print("halt")
