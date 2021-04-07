# -*- coding: utf-8 -*-

"""
Main logic for facilitating the download of a torrent.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from .protocol.file_writer import FileWriter
from .protocol.metainfo import MetaInfoFile
from .protocol.peer import PeerConnection, PeerConnectionStats
from .protocol.piece_handler import PieceRequester
from .protocol.tracker import TrackerConnection
from .. import get_app_config

logger = logging.getLogger(__name__)
MAX_PEER_CONNECTIONS = 2


class Download:
    """
    A torrent currently being downloaded by the Client.
    This wraps the tracker, requester, and peer handling into a single API.
    """

    def __init__(self, torrent_fp: Path, destination: Path, local_peer):
        self.client_info = local_peer
        self.torrent = MetaInfoFile.from_file(torrent_fp, destination)
        self.peer_queue = asyncio.Queue()
        self.piece_queue = asyncio.Queue()
        self.tracker = TrackerConnection(self.client_info, self.torrent, self.peer_queue)
        self.file_writer = FileWriter(self.torrent.files, destination)
        self.download_stats = PeerConnectionStats(0.0, 0, 0, 0)
        self.peers = []
        self.download_task: Optional[asyncio.Task] = None
        self.write_task: Optional[asyncio.Task] = None

    def download(self):
        self.download_stats.started = asyncio.get_event_loop().time()
        self.tracker.start()
        self.download_task = asyncio.create_task(self._download(), name=f"Download for {self.torrent}")
        self.write_task = asyncio.create_task(self._write_files(), name=f"Write task for {self.torrent}")
        return self.download_task

    async def _write_files(self):
        """
        Task that handles writing received pieces to a file.
        """
        try:
            while True:
                piece = await self.piece_queue.get()
                await self.file_writer.write(piece)
                self.piece_queue.task_done()
        except Exception:
            if not self.download_task.cancelled() or not self.download_task.done():
                self.download_task.cancel()

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        piece_requester = PieceRequester(self.torrent, self.piece_queue)
        self.peers = [PeerConnection(self.client_info, self.torrent.info_hash, piece_requester, self.peer_queue,
                                     self.download_stats)
                      for _ in range(MAX_PEER_CONNECTIONS)]

        conf = get_app_config()
        last_speed_check = None
        average_speed = 0.0
        last_downloaded = self.download_stats.downloaded
        try:
            while not self.torrent.complete:
                if last_speed_check is None:
                    last_speed_check = self.download_stats.started
                else:
                    now = asyncio.get_event_loop().time()
                    downloaded = self.download_stats.downloaded

                    time_diff = now - last_speed_check
                    download_diff = downloaded - last_downloaded
                    if time_diff > 2:
                        average_speed = round((download_diff / time_diff) / 2 ** 10, 2)
                        last_speed_check = now
                        last_downloaded = self.download_stats.downloaded

                # TODO: Fix this, smoother CLI/TUI separation.
                # check peers? Re-announce if necessary.
                peers_connected = len(list(filter(lambda x: x.peer is not None, self.peers)))
                pct_complete = round((self.torrent.present / self.torrent.total_size) * 100, 2)
                msg = f"{self.torrent} progress: " \
                      f"{pct_complete} % ({self.torrent.present}/{self.torrent.total_size}b)" \
                      f"\t{peers_connected} peers.\t{average_speed} KB/s 2 sec. speed average."
                if conf.use_cli:
                    print(msg)
                logger.info(msg)

                await asyncio.sleep(2)

                if self.download_task.cancelled():
                    logger.info(f"{self.torrent}: Download task cancelled.")
                    await self.tracker.cancel_announce()
                    break

                if self.tracker.task.cancelled() or self.tracker.task.done():
                    logger.info(f"{self.torrent}: Tracker task cancelled or complete.")
                    break
            else:
                await self.tracker.completed()

        except Exception as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.error(f"{type(e).__name__} exception received in client.download.")
        finally:
            logger.debug(f"Ending download loop and cleaning up.")
            self.write_task.cancel()
            while not self.piece_queue.empty():
                await self.file_writer.write(self.piece_queue.get_nowait())

            total_time = asyncio.get_event_loop().time() - self.download_stats.started
            msg = f"Download stopped! Took {round(total_time, 5)}s" \
                  f"\tDownloaded: {self.download_stats.downloaded}\tUploaded: {self.download_stats.uploaded}" \
                  f"\tEst download speed: {round((self.download_stats.downloaded / total_time) / 2 ** 20, 2)} MB/s"

            if conf.use_cli:
                print(msg)
            logger.info(msg)
