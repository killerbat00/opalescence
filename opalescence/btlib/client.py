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

from .download import Download, Complete
from .protocol.peer import PeerInfo

logger = getLogger(__name__)

MAX_PEER_CONNECTIONS = 5


def _generate_peer_id():
    """
    Generates a 20 byte long unique identifier for our peer.
    TODO: generate dynamically
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
    """
    The client is the main entrypoint for downloading torrents. Add torrents to
    the client and then start it in order to commence downloading.
    """

    def __init__(self):
        self._downloading: Optional[list[Download]] = None
        self._local_peer: Optional[PeerInfo] = None
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._close_task = None
        self._local_peer = PeerInfo(_retrieve_local_ip(), 6881, _generate_peer_id())

    async def start_all(self):
        """
        Starts downloading all current torrents.
        """
        if self._downloading is None or len(self._downloading) == 0:
            raise ClientError("No torrents added.")

        self._running = True

        tasks = []
        for torrent in self._downloading:
            try:
                tasks.append(torrent.download())
            except Complete:
                logger.info(f"{self}: {torrent.torrent.name} already complete.")

        if len(tasks) == 0:
            logger.info(f"{self}: Complete. No torrents to download.")
            return

        self._tasks = set(tasks)

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    def stop(self):
        """
        Creates and schedules a task that will asynchronously
        stop and clean up all running tasks.
        """
        asyncio.create_task(self.stop_all())

    async def stop_all(self):
        """
        Cancels and cleans up all running tasks for this Client.
        """
        if not self._running or len(self._tasks) == 0:
            return

        self._running = False

        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def add_torrent(self, *, torrent_fp: Path = None, destination: Path = None) -> bool:
        """
        Adds a torrent to the Client for downloading.
        :param torrent_fp: The filepath to the .torrent metainfo file.
        :param destination: The destination in which to save the torrent.
        :return: True if successfully added, False otherwise.
        :raises ClientError: if no valid torrent to download or destination specified.
        """
        if destination and destination.exists() and torrent_fp is not None:
            download = Download(torrent_fp, destination, self._local_peer)
            return self._add_torrent(download)
        else:
            raise ClientError("No torrent to download specified.")

    def _add_torrent(self, download: Download) -> bool:
        """
        Actually adds the constructed Download object for the torrent
        to the downloading torrents in this Client.
        :param download: Download object
        :return: True if successfully added.
        """
        if self._downloading is None:
            self._downloading = []
        for t in self._downloading:
            if t.torrent.info_hash == download.torrent.info_hash:  # already in the list
                return True
        self._downloading.append(download)
        return True
