# -*- coding: utf-8 -*-

from __future__ import annotations

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""

__all__ = ['ClientError', 'ClientTorrent']

import asyncio
import logging
import secrets
import socket
from logging import getLogger
from typing import Optional, Set

from .metainfo import MetaInfoFile
from .protocol.peer import PeerConnection, PeerInfo
from .protocol.piece_handler import PieceRequester, FileWriter
from .tracker import TrackerManager, TrackerConnectionError

logger = getLogger(__name__)

MAX_PEER_CONNECTIONS = 5
PEER_ID = b'-OP0001-777605734135'  # should generate this once.
LOCAL_IP = "10.10.2.105"
LOCAL_PORT = 6881


def _generate_peer_id():
    """
    Generates a 20 byte long unique identifier for our peer.
    :return: our unique peer ID
    """
    return f"-OP0001-{secrets.token_urlsafe(12)}".encode("UTF-8")


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
        self._downloading: Optional[list[ClientTorrent]] = None
        self._local_peer: Optional[PeerInfo] = None
        self._running = False
        self._tasks: Set[asyncio.Task] = set()
        self._setup()

    def _setup(self):
        assert not self._running, "Can't setup already running Client."
        local_peer_id = _generate_peer_id()
        local_ip = _retrieve_local_ip()
        self._local_peer = PeerInfo(local_ip, LOCAL_PORT, local_peer_id)
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
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    def add_torrent(self, *, torrent: MetaInfoFile = None, torrent_fp: str = None, destination: str = None) -> bool:
        if destination is None:
            raise ClientError("No download destination specified.")

        if torrent is not None:
            return self._add_torrent_metainfo(torrent, destination)
        elif torrent_fp is not None:
            return self._add_torrent_filepath(torrent_fp, destination)
        else:
            raise ClientError("No torrent to download specified.")

    def _add_torrent_metainfo(self, torrent: MetaInfoFile, destination: str) -> bool:
        ct = ClientTorrent(torrent, destination)
        return self._add_torrent(ct)

    def _add_torrent_filepath(self, torrent_fp: str, destination: str) -> bool:
        ct = ClientTorrent(MetaInfoFile.from_file(torrent_fp), destination)
        return self._add_torrent(ct)

    def _add_torrent(self, ct: ClientTorrent):
        if self._downloading is None:
            self._downloading = []
        for t in self._downloading:
            if t.torrent.info_hash == ct.torrent.info_hash:
                return False
        self._downloading.append(ct)
        return True


class ClientTorrent:
    """
    A torrent currently being handled by the client. This wraps the tracker, requester, and peers into a single
    API.
    """

    def __init__(self, torrent: MetaInfoFile, destination: str):
        self.client_info = PeerInfo(LOCAL_IP, LOCAL_PORT, PEER_ID)
        self.torrent = torrent
        self.stats = {"uploaded": 0, "downloaded": 0, "left": torrent.total_size, "started": 0.0}
        self.tracker = TrackerManager(self.client_info, torrent, self.stats)
        self.peer_q = asyncio.Queue()
        self.writer = FileWriter(torrent, destination)
        self.peers = []
        self.abort = False
        self.task = None

        def download_complete():
            self.stop()
            total_time = asyncio.get_event_loop().time() - self.stats['started']
            log = logging.getLogger("opalescence")
            old_level = log.getEffectiveLevel()
            logger.setLevel(logging.INFO)
            logger.info(f"Download stopped! Took {round(total_time, 5)}s")
            logger.info(f"Downloaded: {self.stats['downloaded']} Uploaded: {self.stats['uploaded']}")
            logger.info(f"Est download speed: "
                        f"{round((self.stats['downloaded'] / total_time) / 2 ** 20, 2)} MB/s")
            log.setLevel(old_level)

            if self.writer:
                self.writer.close_files()

        self.download_complete_cb = download_complete
        self.requester = PieceRequester(torrent, self.writer, self.download_complete_cb, self.stats)

    def stop(self):
        if self.task:
            self.task.cancel()

    def download(self):
        self.stats["started"] = asyncio.get_event_loop().time()
        self.task = asyncio.create_task(self.download_coro(), name=f"ClientTorrent for {self.torrent}")
        return self.task

    async def download_coro(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        TODO: needs work
        """
        previous = None
        interval = self.tracker.DEFAULT_INTERVAL
        self.peers = [PeerConnection(PeerInfo(LOCAL_IP, LOCAL_PORT, PEER_ID), self.torrent.info_hash, self.requester,
                                     self.peer_q)
                      for _ in range(MAX_PEER_CONNECTIONS)]

        try:
            while True:
                if self.requester.complete:
                    await self.tracker.completed()
                    self.download_complete_cb()
                    break

                if self.abort:
                    logger.info(f"Aborting download of {self.torrent.name}. Downloaded {self.stats['downloaded']} "
                                f"bytes")
                    await self.tracker.cancel()
                    self.download_complete_cb()
                    break

                current = asyncio.get_running_loop().time()
                if (not previous) or (previous + interval < current):
                    try:
                        response = await self.tracker.announce()
                    except TrackerConnectionError:
                        self.abort = True
                        continue

                    if response:
                        previous = current
                        if response.interval:
                            interval = response.interval

                        while not self.peer_q.empty():
                            self.peer_q.get_nowait()

                        for peer in response.get_peers():
                            if peer[0] == self.client_info.ip:
                                if peer[1] == self.client_info.port:
                                    logger.info(f"Ignoring peer. It's us...")
                                    continue
                            self.peer_q.put_nowait(PeerInfo(peer[0], peer[1]))
                else:
                    await asyncio.sleep(interval)
        except (asyncio.CancelledError, Exception) as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"{type(e).__name__} exception received in client.download.")
                logger.exception(e, exc_info=True)
                logger.info(f"Downloaded: {self.stats['downloaded']} Uploaded: {self.stats['uploaded']}")
            else:
                self.download_complete_cb()
                await self.tracker.cancel()
        finally:
            logger.debug(f"Ending download loop. Cleaning up.")
            for peer in self.peers:
                peer.stop_forever()
