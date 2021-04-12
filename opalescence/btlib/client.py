# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""

from __future__ import annotations

__all__ = ['ClientError', 'Client']

import asyncio
import contextlib
import socket
from logging import getLogger
from pathlib import Path
from typing import Optional, Set

from .protocol.peer_info import PeerInfo
from .torrent import Torrent

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
    the client and then start it in order to commence downloading. The client doesn't
    currently monitor or supervise downloading torrents.

    It has not been validated to work when downloading >1 torrent.
    """

    def __init__(self):
        self._task = None
        self._tasks: Set[asyncio.Task] = set()
        self._running = False
        self.downloading: Optional[list[Torrent]] = None
        self._local_peer = PeerInfo(_retrieve_local_ip(), 6881, _generate_peer_id())

    def start(self):
        """
        Creates an schedules a task that will start all downloads.
        """
        if not self._running:
            self._running = True
            self._task = asyncio.create_task(self.start_all())

    def stop(self):
        """
        Creates and schedules a task that will asynchronously
        cancel all running downloads.
        """
        if self._running:
            asyncio.create_task(self._stop_all())

    async def _stop_all(self):
        """
        Cancels and cleans up all running tasks for this client.
        """
        if not self._running or len(self._tasks) == 0:
            return

        self._running = False

        for t in self._tasks:
            t.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def _add_task(self, task: asyncio.Task):
        """
        Adds a task to the list of running tasks.
        :param task: task to add to this borg.
        """
        if task is None or task.cancelled() or task.done() or self._running:
            return
        self._tasks.add(task)

    async def start_all(self):
        """
        Starts downloading all current torrents.
        """
        if self.downloading is None or len(self.downloading) == 0:
            raise ClientError

        for download in self.downloading:
            self._add_task(download.download())

        if len(self._tasks) == 0:
            logger.info("Complete. No torrents to download")
            return

        try:
            # TODO: we return as soon as any download errors. Revisit this.
            await asyncio.gather(*self._tasks, return_exceptions=True)
        except Exception as exc:
            logger.error("%s received in client:start_all" % type(exc).__name__)

        self._running = False

    def add_torrent(self, *, torrent_fp: Path = None, destination: Path = None):
        """
        Adds a torrent to the Client for downloading.
        :param torrent_fp: The filepath to the .torrent metainfo file.
        :param destination: The destination in which to save the torrent.
        """
        if self._running:
            return

        download = Torrent(torrent_fp, destination, self._local_peer)
        if self.downloading is None:
            self.downloading = []

        def exists(d):
            return d.torrent.info_hash == download.torrent.info_hash

        if any(filter(exists, self.downloading)):
            return

        self.downloading.append(download)
