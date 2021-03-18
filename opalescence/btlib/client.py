# -*- coding: utf-8 -*-
"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""

from __future__ import annotations

__all__ = ['ClientError', 'Client']

import asyncio
import socket
from logging import getLogger
from pathlib import Path
from typing import Optional, Set

from .download import Download
from .metainfo import MetaInfoFile
from .protocol.peer import PeerInfo

logger = getLogger(__name__)

MAX_PEER_CONNECTIONS = 5


def _generate_peer_id():
    """
    Generates a 20 byte long unique identifier for our peer.
    :return: our unique peer ID
    """
    return f"-OP0001-010929102910".encode("UTF-8")


def _retrieve_local_ip():
    """
    Retrieves the local IP of this computer.
    TODO: Retrieve/implement STUN/UPNP for sending data.
    :return: local IP
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't even have to be reachable
        s.connect(('10.255.255.255', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class Client:
    def __init__(self):
        self._downloading: Optional[list[Download]] = None
        self._local_peer: Optional[PeerInfo] = None
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._setup()

    def _setup(self):
        assert not self._running, "Can't setup already running Client."
        local_peer_id = _generate_peer_id()
        local_ip = _retrieve_local_ip()
        self._local_peer = PeerInfo(local_ip, 6881, local_peer_id)
        # setup signal handler/loop?

    async def start_all(self):
        if self._downloading is None or len(self._downloading) == 0:
            raise ClientError("No torrents added.")

        self._running = True

        self._tasks = [torrent.download() for torrent in self._downloading]
        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            logger.info(f"{self}: Cancelled in start_all.")

    def stop(self):
        asyncio.get_running_loop().run_until_complete(self.stop_all())

    async def stop_all(self):
        if not self._running:
            return
        self._running = False
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def add_torrent(self, *, torrent: MetaInfoFile = None, torrent_fp: Path = None, destination: Path = None) -> bool:
        if destination is None or not destination.exists():
            raise ClientError("No download destination specified.")

        if torrent is not None:
            return self._add_torrent_metainfo(torrent, destination)
        elif torrent_fp is not None:
            return self._add_torrent_filepath(torrent_fp, destination)
        else:
            raise ClientError("No torrent to download specified.")

    def _add_torrent_metainfo(self, torrent: MetaInfoFile, destination: Path) -> bool:
        ct = Download(torrent, destination, self._local_peer)
        return self._add_torrent(ct)

    def _add_torrent_filepath(self, torrent_fp: Path, destination: Path) -> bool:
        ct = Download(MetaInfoFile.from_file(torrent_fp), destination, self._local_peer)
        return self._add_torrent(ct)

    def _add_torrent(self, ct: Download):
        if self._downloading is None:
            self._downloading = []
        for t in self._downloading:
            if t.torrent.info_hash == ct.torrent.info_hash:  # already in the list
                return False
        self._downloading.append(ct)
        return True
