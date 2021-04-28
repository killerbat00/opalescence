# -*- coding: utf-8 -*-

"""
Main logic for facilitating the download of a torrent.
"""

import asyncio
import functools
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

from .protocol.errors import FileWriterError
from .protocol.fileio import FileWriter
from .protocol.metainfo import MetaInfoFile
from .protocol.peer import PeerConnectionPool
from .protocol.peer_info import PeerInfo
from .protocol.tracker import TrackerTask
from .. import get_app_config

logger = logging.getLogger(__name__)


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
                 local_peer: PeerInfo, event: asyncio.Event):
        self.status = DownloadStatus.NotStarted

        self.conf = get_app_config()

        self.torrent = MetaInfoFile.from_file(torrent_fp, destination)
        self.client_info = PeerInfo.from_instance(local_peer)

        self.peer_queue = asyncio.Queue()
        self.piece_queue = asyncio.Queue()

        self.peer_pool: PeerConnectionPool = PeerConnectionPool(self.client_info,
                                                                self.torrent,
                                                                self.peer_queue,
                                                                self.piece_queue,
                                                                self.conf.max_peers)
        self.file_writer: FileWriterTask = FileWriterTask(self.torrent,
                                                          self.piece_queue)
        self.tracker: TrackerTask = TrackerTask(self.client_info, self.torrent,
                                                self.peer_queue)

        self.monitor_task: Optional[asyncio.Task] = None
        self.download_started = 0.0
        self.total_time = 0.0
        self.average_speed = 0.0
        self.started_with = 0
        self.completed_event = event

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
        logger.info("Checking existing pieces...")
        self.torrent.check_existing_pieces()
        logger.info("We have %s / %s bytes" % (self.torrent.present,
                                               self.torrent.total_size))

        self.download_started = asyncio.get_event_loop().time()
        self.started_with = self.torrent.present
        if not self.torrent.complete:
            self.status = DownloadStatus.CollectingPeers
            self.tracker.start()
            self.monitor_task = asyncio.create_task(self._download(),
                                                    name=f"Torrent task for {self.torrent}")
            return self.monitor_task
        else:
            self.status = DownloadStatus.Completed
            self.completed_event.set()

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
                    if task.cancelled():
                        logger.info("%s: %s _task cancelled." % (self.torrent, name))
                        raise TorrentError

                await asyncio.sleep(.5)
            else:
                self.status = DownloadStatus.Completed
                self.completed_event.set()
                asyncio.create_task(self.tracker.completed())

        except Exception as e:
            self.status = DownloadStatus.Errored
            if not isinstance(e, asyncio.CancelledError):
                logger.error("%s exception received in Torrent.download." % type(
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


class FileWriterTask(FileWriter):
    """
    This subclass of `FileWriter` accepts a queue where completed pieces are sent and
    handles writing those pieces to disk.
    """

    def __init__(self, torrent: MetaInfoFile, piece_queue: asyncio.Queue):
        super().__init__(torrent.files, torrent.piece_length)
        self._queue: asyncio.Queue = piece_queue
        self._lock = asyncio.Lock()
        self.task: asyncio.Task = asyncio.create_task(self._write_pieces())

    def stop(self):
        """
        Stops the piece writing task.
        """
        if self.task:
            self.task.cancel()

    async def _write_pieces(self):
        """
        Coroutine scheduled as a task via `start` that consumes completed
        pieces from the piece_queue and writes them to file.
        """
        piece = None
        try:
            while True:
                piece = await self._queue.get()
                asyncio.create_task(self._await_write(piece))
                self._queue.task_done()
        except Exception as exc:
            logger.error("Encountered %s exception writing %s" %
                         (type(exc).__name__, piece))
            if not isinstance(exc, FileWriterError):
                raise FileWriterError from exc
            raise
        finally:
            self.close_files()

    async def _await_write(self, piece):
        """
        Schedules and awaits for the task in the executor responsible
        for writing the piece. Marks the piece complete on success.

        :param piece: piece to write
        """
        self.open_files()
        if not self._fps:
            raise FileWriterError("Unable to open files.")

        await self._lock.acquire()

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, functools.partial(
                self._write_piece_data, piece))
            piece.mark_written()  # purge from memory
        except Exception as e:
            logger.error(e)
            if not isinstance(e, FileWriterError):
                raise FileWriterError from e
            raise
        finally:
            self._lock.release()
