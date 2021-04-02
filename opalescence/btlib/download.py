import asyncio
import logging
from pathlib import Path

from .metainfo import MetaInfoFile
from .protocol.peer import PeerConnection
from .protocol.piece_handler import FileWriter, PieceRequester
from .tracker import TrackerConnection, TrackerStats, TrackerConnectionError

logger = logging.getLogger(__name__)
MAX_PEER_CONNECTIONS = 5


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
        self.tracker = None
        self.writer = FileWriter(self.torrent)
        self.requester = PieceRequester(self.torrent, self.writer, self.stats)

        self.peers = []
        self.abort = False

    def download_complete(self):
        total_time = asyncio.get_event_loop().time() - self.stats.started
        logger.info(f"Download stopped! Took {round(total_time, 5)}s")
        logger.info(f"Downloaded: {self.stats.downloaded} Uploaded: {self.stats.uploaded}")
        logger.info(f"Est download speed: {round((self.stats.downloaded / total_time) / 2 ** 20, 2)} MB/s")

    def download(self):
        self.stats.started = asyncio.get_event_loop().time()
        self.tracker = TrackerConnection(self.client_info, self.torrent, self.stats, self.peer_queue)
        self.tracker.start()
        return asyncio.create_task(self._download(), name=f"Download for {self.torrent}")

    async def _download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        """
        self.peers = [PeerConnection(self.client_info, self.torrent.info_hash, self.requester, self.peer_queue)
                      for _ in range(MAX_PEER_CONNECTIONS)]
        try:
            while not self.requester.complete:
                await asyncio.sleep(0.5)

        except (asyncio.CancelledError, Exception) as e:
            if not isinstance(e, asyncio.CancelledError):
                logger.debug(f"{type(e).__name__} exception received in client.download.")
                logger.exception(e, exc_info=True)
            if not isinstance(e, TrackerConnectionError):
                await self.tracker.cancel_announce()
        finally:
            self.tracker.task.cancel()
            await self.tracker.completed()
            self.download_complete()
            logger.debug(f"Ending download loop and cleaning up.")
            for peer in self.peers:
                peer.stop_forever()
