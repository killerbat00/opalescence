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


class BorgError(Exception):
    """
    Raised when the client encounters an error
    """


class BorgTask:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._tasks: Set[asyncio.Task] = set()

    async def start(self):
        """
        Starts all tasks this borg is controlling.
        """
        if self._tasks is None or len(self._tasks) == 0:
            return

        self._running = True

        try:
            await asyncio.gather(*self._tasks)
        except asyncio.CancelledError:
            pass

    def stop(self):
        """
        Creates and schedules a task that will asynchronously
        stop and clean up all running tasks.
        """
        self._tasks.add(asyncio.create_task(self.stop_all()))

    async def stop_all(self):
        """
        Cancels and cleans up all running tasks for this BorgTask.
        """
        if not self._running or len(self._tasks) == 0:
            return

        self._running = False

        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def add_task(self, task: asyncio.Task):
        """
        Adds a task to the list of running tasks.
        :param task: task to add to this borg.
        """
        if task is None or task.cancelled() or task.done():
            return
        self._tasks.add(task)


class Client(BorgTask):
    """
    The client is the main entrypoint for downloading torrents. Add torrents to
    the client and then start it in order to commence downloading.
    """

    def __init__(self):
        super().__init__()
        self._downloading: Optional[list[Download]] = None
        self._local_peer = PeerInfo(_retrieve_local_ip(), 6881, _generate_peer_id())

    async def start_all(self):
        """
        Starts downloading all current torrents.
        """
        if self._downloading is None or len(self._downloading) == 0:
            raise ClientError("No torrents added.")

        for download in self._downloading:
            download.torrent.check_existing_pieces()
            logger.info(f"We have {download.torrent.present} / {download.torrent.total_size} bytes.")
            if download.torrent.present == download.torrent.total_size:
                logger.info(f"{self}: {download.torrent.name} already complete.")
                continue
            self.add_task(download.download())

        if len(self._tasks) == 0:
            logger.info(f"{self}: Complete. No torrents to download.")
            return

        await super().start()

    def add_torrent(self, *, torrent_fp: Path = None, destination: Path = None):
        """
        Adds a torrent to the Client for downloading.
        :param torrent_fp: The filepath to the .torrent metainfo file.
        :param destination: The destination in which to save the torrent.
        :return: True if successfully added, False otherwise.
        :raises ClientError: if no valid torrent to download or destination specified.
        """
        if destination and destination.exists() and torrent_fp is not None:
            download = Download(torrent_fp, destination, self._local_peer)
            self._add_torrent(download)
        else:
            raise ClientError("No torrent to download specified.")

    def _add_torrent(self, download: Download):
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
                return
        self._downloading.append(download)
        return
