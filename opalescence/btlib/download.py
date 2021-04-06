# -*- coding: utf-8 -*-

"""
Main logic for facilitating the download of a torrent.
"""

import asyncio
import logging
from pathlib import Path

from .protocol.metainfo import MetaInfoFile, FileWriter
from .protocol.peer import PeerConnection, PeerConnectionStats
from .protocol.piece_handler import PieceRequester
from .protocol.tracker import TrackerConnection

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
        self.download_stats = PeerConnectionStats(0.0, 0, 0)
        self.peers = []
        self.download_task = None

    def download(self):
        self.download_stats.started = asyncio.get_event_loop().time()
        self.tracker.start()
        self.download_task = asyncio.create_task(self._download(), name=f"Download for {self.torrent}")
        return self.download_task

    async def _write_files(self):
        try:
            while True:
                piece = await self.piece_queue.get()
                await self.file_writer.write(piece)
        except Exception:
            raise

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        piece_requester = PieceRequester(self.torrent, self.piece_queue)
        self.peers = [PeerConnection(self.client_info, self.torrent.info_hash, piece_requester, self.peer_queue,
                                     self.download_stats)
                      for _ in range(MAX_PEER_CONNECTIONS)]

        peers_connected = 0
        last_speed_check = None
        average_speed = 0
        last_downloaded = self.download_stats.downloaded
        write_task = asyncio.create_task(self._write_files(), name=f"Write task for {self.torrent}")
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
                        average_speed = round((download_diff / time_diff) / 2 ** 10, 5)
                        last_speed_check = now
                        last_downloaded = self.download_stats.downloaded

                logger.info(f"{self.torrent} progress: {self.torrent.present}/{self.torrent.total_size} bytes."
                            f"\t{peers_connected} peers.\t{average_speed} KB/s 2 sec. speed average.")

                await asyncio.sleep(1)

                # check peers? Re-announce if necessary.
                # peers_connected = len(list(filter(lambda x: x.peer is not None, self.peers)))

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
            write_task.cancel()
        finally:
            logger.debug(f"Ending download loop and cleaning up.")

            total_time = asyncio.get_event_loop().time() - self.download_stats.started
            logger.info(f"Download stopped! Took {round(total_time, 5)}s")
            logger.info(f"Downloaded: {self.download_stats.downloaded} Uploaded: {self.download_stats.uploaded}")
            logger.info(f"Est download speed: {round((self.download_stats.downloaded / total_time) / 2 ** 20, 2)} MB/s")
