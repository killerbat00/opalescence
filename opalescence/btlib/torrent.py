# -*- coding: utf-8 -*-

"""
Main logic for facilitating the download of a torrent.
"""

import asyncio
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

from .protocol.fileio import FileWriterTask
from .protocol.metainfo import MetaInfoFile
from .protocol.peer import PeerConnectionPool
from .protocol.peer_info import PeerInfo
from .protocol.tracker import TrackerTask
from .. import get_app_config

logger = logging.getLogger(__name__)
MAX_PEER_CONNECTIONS = 2


class DownloadStatus(Enum):
    Errored = -1
    NotStarted = 0
    CollectingPeers = 1
    Downloading = 2
    Completed = 3
    Stopped = 4


class TorrentError(Exception):
    pass


class Torrent:
    """
    A torrent currently being downloaded by the client.
    This wraps the tracker, requester, and peer handling into a single API.
    """

    def __init__(self, torrent_fp: Path, destination: Path,
                 local_peer: PeerInfo):
        self.status = DownloadStatus.NotStarted

        self.conf = get_app_config()

        self.torrent = MetaInfoFile.from_file(torrent_fp, destination)
        self.client_info = PeerInfo.from_instance(local_peer)

        self.peer_queue = asyncio.Queue()
        self.piece_queue = asyncio.Queue()

        # TODO: Move this. Currently PeerConnectionPool -> PieceRequester
        # and PieceRequester looks at the torrent's pieces, expecting them to
        # be marked complete if they are. Without this here, we'll request
        # pieces we already have. It's mostly fine because we disregard the blocks
        # when we receive them, but not ideal.
        logger.info("Checking existing pieces...")
        self.torrent.check_existing_pieces()
        self.peer_pool: PeerConnectionPool = PeerConnectionPool(self.client_info,
                                                                self.torrent,
                                                                self.peer_queue,
                                                                self.piece_queue,
                                                                self.conf.max_peers)
        self.file_writer: FileWriterTask = FileWriterTask(self.torrent.files,
                                                          self.piece_queue)
        self.tracker: TrackerTask = TrackerTask(self.client_info, self.torrent,
                                                self.peer_queue)

        self.monitor_task: Optional[asyncio.Task] = None
        self.download_started = 0.0
        self.total_time = 0.0
        self.average_speed = 0.0
        self.started_with = 0

    @property
    def name(self):
        return self.torrent.name

    @property
    def present(self):
        return self.started_with + self.peer_pool.stats.torrent_bytes_downloaded

    @property
    def total_size(self):
        return self.torrent.total_size

    @property
    def pct_complete(self):
        return round((self.present / self.total_size) * 100, 2)

    @property
    def num_peers(self):
        return self.peer_pool.num_connected

    def download(self):
        self.download_started = asyncio.get_event_loop().time()

        logger.info("We have %s / %s bytes" % (self.torrent.present,
                                               self.torrent.total_size))
        self.started_with = self.torrent.present
        if not self.torrent.complete:
            self.status = DownloadStatus.CollectingPeers
            self.tracker.start()
            self.file_writer.start()
            self.monitor_task = asyncio.create_task(self._download(),
                                                    name=f"Torrent task for {self.torrent}")
            return self.monitor_task
        else:
            self.status = DownloadStatus.Completed

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        tasks = {"Monitor": self.monitor_task,
                 "Tracker": self.tracker.task,
                 "FileWriter": self.file_writer.task}
        last_time = 0.0
        last_downloaded = 0
        last_time_no_peers = 0.0
        try:
            while not self.torrent.complete:
                now = asyncio.get_event_loop().time()

                if not last_time:
                    last_time = self.download_started
                elif not last_downloaded:
                    last_downloaded = self.peer_pool.stats.bytes_downloaded
                else:
                    dt = now - last_time
                    diff = self.peer_pool.stats.bytes_downloaded - last_downloaded
                    self.average_speed = round((diff / dt) / 2 ** 10, 2)

                # monitor tasks
                for name, task in tasks.items():
                    if task.cancelled() or task.done():
                        logger.info("%s: %s _task cancelled." % (self.torrent, name))
                        if name == "Tracker":
                            await self.tracker.cancel_announce()
                        raise TorrentError

                if self.num_peers == 0:
                    if not last_time_no_peers:
                        last_time_no_peers = now
                    else:
                        if now - last_time_no_peers >= 3:
                            self.tracker.retrieve_more_peers()
                            last_time_no_peers = None

                await asyncio.sleep(.5)
            else:
                self.status = DownloadStatus.Completed
                await self.tracker.completed()

        except Exception as e:
            self.status = DownloadStatus.Errored
            if not isinstance(e, asyncio.CancelledError):
                logger.error("%s exception received in client.download." % type(
                    e).__name__)
        finally:
            if self.status != DownloadStatus.Errored:
                self.status = DownloadStatus.Stopped
            logger.debug(f"Ending download loop and cleaning up.")
            self.tracker.stop()
            self.peer_pool.stop()
            self.file_writer.stop()

            now = asyncio.get_event_loop().time()
            self.total_time = now - self.download_started
