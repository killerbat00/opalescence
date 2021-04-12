# -*- coding: utf-8 -*-

"""
Contains basic information about a peer.
"""

from typing import Optional


class PeerInfo:
    def __init__(self, ip: str, port: int, peer_id: Optional[bytes] = None):
        self.ip: str = ip
        self.port: int = port
        self._peer_id: Optional[bytes] = peer_id
        self.choking = True
        self.interested = False

    def __eq__(self, other):
        # TODO: check equality across info hashes
        return (isinstance(other, PeerInfo)
                and self.ip == other.ip
                and self.port == other.port)

    def __str__(self):
        return f"{self.ip}:{self.port}"

    def __hash__(self):
        return hash(str(self))

    def reset_state(self):
        self.choking = True
        self.interested = False

    @classmethod
    def from_instance(cls, other):
        return cls(other.ip, other.port, other.peer_id_bytes)

    @property
    def peer_id_bytes(self) -> bytes:
        if self._peer_id:
            return self._peer_id

    @property
    def peer_id(self) -> str:
        return str(self)

    @peer_id.setter
    def peer_id(self, val):
        if isinstance(val, bytes):
            self._peer_id = val
