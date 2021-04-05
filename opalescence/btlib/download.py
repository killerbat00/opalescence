import asyncio
import logging
from pathlib import Path

from .metainfo import MetaInfoFile
from .protocol.peer import PeerConnection
from .protocol.piece_handler import PieceRequester
from .tracker import TrackerConnection, TrackerStats

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
        self.stats = TrackerStats(0, self.torrent.present, self.torrent.remaining, 0.0)
        self.peer_queue = asyncio.Queue()
        self.tracker = TrackerConnection(self.client_info, self.torrent, self.stats, self.peer_queue)
        self.requester = PieceRequester(self.torrent, self.stats)
        self.peers = []
        self.download_task = None

    def download(self):
        self.stats.started = asyncio.get_event_loop().time()
        self.tracker.start()
        self.download_task = asyncio.create_task(self._download(), name=f"Download for {self.torrent}")
        return self.download_task

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        self.peers = [PeerConnection(self.client_info, self.torrent.info_hash, self.requester, self.peer_queue)
                      for _ in range(MAX_PEER_CONNECTIONS)]
        try:
            while not self.torrent.complete:
                logger.info(f"{self.torrent} progress: {self.torrent.present}/{self.torrent.total_size} bytes. "
                            f"{self.torrent.remaining} left.")

                await asyncio.sleep(1)

                # check peers? Re-announce if necessary.

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
                logger.debug(f"{type(e).__name__} exception received in client.download.")
                logger.exception(e, exc_info=True)
        finally:
            logger.debug(f"Ending download loop and cleaning up.")
            self.tracker.task.cancel()
            for peer in self.peers:
                peer.stop_forever()

            total_time = asyncio.get_event_loop().time() - self.stats.started
            logger.info(f"Download stopped! Took {round(total_time, 5)}s")
            logger.info(f"Downloaded: {self.stats.downloaded} Uploaded: {self.stats.uploaded}")
            logger.info(f"Est download speed: {round((self.stats.downloaded / total_time) / 2 ** 20, 2)} MB/s")
