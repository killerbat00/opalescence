# -*- coding: utf-8 -*-

"""
Main logic for facilitating the download of a torrent.
"""

import asyncio
import dataclasses
import logging
from enum import Enum
from pathlib import Path
from typing import Optional

from .events import Observer, Event
from .protocol.fileio import FileWriter
from .protocol.metainfo import MetaInfoFile
from .protocol.peer import PeerConnectionPool
from .protocol.peer_info import PeerInfo
from .protocol.piece_handler import PieceRequester, PieceReceivedEvent
from .protocol.tracker import TrackerConnection, PeersReceivedEvent
from .. import get_app_config

logger = logging.getLogger(__name__)
MAX_PEER_CONNECTIONS = 2


@dataclasses.dataclass
class DownloadStats:
    average_speed: float = 0.0
    pct_complete: float = 0.0
    present: int = 0
    total_size: int = 0
    num_peers: int = 0
    download_started: float = 0.0
    last_updated: float = 0.0


class DownloadStatus(Enum):
    Errored = -1
    NotStarted = 0
    Downloading = 1
    Completed = 2


class DownloadEvent(Event):
    def __init__(self, name, data):
        super().__init__(name, data)


class Download(Observer):
    """
    A torrent currently being total_downloaded by the Client.
    This wraps the tracker, requester, and peer handling into a single public API.
    """

    def __init__(self, torrent_fp: Path, destination: Path, local_peer: PeerInfo):
        super().__init__()

        self.status = DownloadStatus.NotStarted
        self.client_info = local_peer
        self.torrent = MetaInfoFile.from_file(torrent_fp, destination)
        self.peer_queue = asyncio.Queue()
        self.piece_queue = asyncio.Queue()
        self.tracker = TrackerConnection(self.client_info, self.torrent)
        self.conf = get_app_config()

        piece_requester = PieceRequester(self.torrent, self.piece_queue)
        self.peer_pool = PeerConnectionPool(self.client_info, self.torrent.info_hash, self.peer_queue,
                                            self.conf.max_peers,
                                            piece_requester)
        self.download_stats = DownloadStats()
        self.download_task: Optional[asyncio.Task] = None

        self.file_writer = FileWriter(self.torrent.files)

        self.register(PeersReceivedEvent, self.add_peers_to_queue)
        self.register(PieceReceivedEvent, self.file_writer.write_piece)

    def add_peers_to_queue(self, peer_list: list[PeerInfo]):
        """
        Adds the given peers to the peer queue.
        :param peer_list: list of `PeerInfo`
        """
        logger.info("Adding more peers to queue.")
        # we only add peers if the list we receive is bigger than the list we have.
        if peer_list is None or len(peer_list) < self.peer_queue.qsize():
            return

        while not self.peer_queue.empty():
            self.peer_queue.get_nowait()

        for peer in peer_list:
            self.peer_queue.put_nowait(peer)

    def download(self):
        self.download_stats.download_started = asyncio.get_event_loop().time()
        self.download_stats.last_updated = self.download_stats.download_started
        self.tracker.start()
        self.download_task = asyncio.create_task(self._download(), name=f"Download task for {self.torrent}")
        return self.download_task

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        try:
            while not self.torrent.complete:
                # TODO: Fix this, smoother CLI/TUI separation.
                # TODO: check peers? Re-announce if necessary.
                peers_connected = self.peer_pool.num_connected
                pct_complete = round((self.torrent.present / self.torrent.total_size) * 100, 2)
                average_speed = 0.0
                msg = f"{self.torrent} progress: " \
                      f"{pct_complete} % ({self.torrent.present}/{self.torrent.total_size}b)" \
                      f"\t{peers_connected} peers.\t{average_speed} KB/s 2 sec. speed average."
                if self.conf.use_cli:
                    print(msg)
                logger.info(msg)

                await asyncio.sleep(2)

                if self.download_task.cancelled():
                    logger.info("%s: Download task cancelled." % self.torrent)
                    await self.tracker.cancel_announce()
                    break

                if self.tracker.task.cancelled() or self.tracker.task.done():
                    logger.info("%s: Tracker task cancelled or complete." % self.torrent)
                    break
            else:
                await self.tracker.completed()

        except Exception as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.error("%s exception received in client.download." % type(e).__name__)
        finally:
            logger.debug(f"Ending download loop and cleaning up.")
            self.tracker.task.cancel()
            self.peer_pool.stop()
            self.file_writer.close()

            total_time = asyncio.get_event_loop().time() - self.download_stats.download_started
            msg = f"Download stopped! Took {round(total_time, 5)}s" \
                  f"\tDownloaded: {self.peer_pool.stats.total_downloaded}\tUploaded:" \
                  f" {self.peer_pool.stats.total_uploaded}" \
                  f"\tEst download speed: " \
                  f"{round((self.peer_pool.stats.total_downloaded / total_time) / 2 ** 20, 2)} MB/s"

            if self.conf.use_cli:
                print(msg)
            logger.info(msg)
