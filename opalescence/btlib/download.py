# -*- coding: utf-8 -*-

"""
Main logic for facilitating the download of a torrent.
"""

import asyncio
import contextlib
import dataclasses
import logging
from pathlib import Path
from typing import Optional

from .protocol.file_writer import FileWriter
from .protocol.metainfo import MetaInfoFile
from .protocol.peer import PeerPool
from .protocol.piece_handler import PieceRequester
from .protocol.tracker import TrackerConnection
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


class Download:
    """
    A torrent currently being total_downloaded by the Client.
    This wraps the tracker, requester, and peer handling into a single public API.
    """

    def __init__(self, torrent_fp: Path, destination: Path, local_peer):
        self.client_info = local_peer
        self.torrent = MetaInfoFile.from_file(torrent_fp, destination)
        # peers are placed into and retrieved from this queue as needed
        self.peer_queue = asyncio.Queue()
        # pieces are placed into this queue and written to disck from this queue
        self.piece_queue = asyncio.Queue()
        self.tracker = TrackerConnection(self.client_info, self.torrent, self.peer_queue)
        self.conf = get_app_config()

        piece_requester = PieceRequester(self.torrent, self.piece_queue)
        self.peer_pool = PeerPool(self.client_info, self.torrent.info_hash, self.peer_queue, self.conf.max_peers,
                                  piece_requester)
        self.download_stats = DownloadStats()
        self.download_task: Optional[asyncio.Task] = None
        self.write_task: Optional[asyncio.Task] = None

    def download(self):
        self.download_stats.download_started = asyncio.get_event_loop().time()
        self.download_stats.last_updated = self.download_stats.download_started
        self.tracker.start()
        self.download_task = asyncio.create_task(self._download(), name=f"Download task for {self.torrent}")
        self.write_task = asyncio.create_task(self._write_received_pieces(), name=f"Write task for {self.torrent}")
        return self.download_task

    async def _write_received_pieces(self):
        """
        Task that handles writing received pieces to a file.
        """
        try_write_on_exc = True

        with FileWriter(self.torrent.files) as file_writer:
            try:
                while True:
                    piece = await self.piece_queue.get()
                    await file_writer.write(piece)
                    self.piece_queue.task_done()
            except Exception as exc:
                if not self.download_task.cancelled() or not self.download_task.done():
                    self.download_task.cancel()
                if isinstance(exc, asyncio.CancelledError):
                    try_write_on_exc = False
            finally:
                if try_write_on_exc:
                    with contextlib.suppress(Exception):
                        while not self.piece_queue.empty():
                            await file_writer.write(self.piece_queue.get_nowait())

    def _try_update_stats(self):
        pass

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        self.peer_pool.start()

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
            self.tracker.task.cancel()
            self.peer_pool.stop()

            total_time = asyncio.get_event_loop().time() - self.download_stats.download_started
            msg = f"Download stopped! Took {round(total_time, 5)}s" \
                  f"\tDownloaded: {self.peer_pool.stats.total_downloaded}\tUploaded:" \
                  f" {self.peer_pool.stats.total_uploaded}" \
                  f"\tEst download speed: " \
                  f"{round((self.peer_pool.stats.total_downloaded / total_time) / 2 ** 20, 2)} MB/s"

            if self.conf.use_cli:
                print(msg)
            logger.info(msg)
