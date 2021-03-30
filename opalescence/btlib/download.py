import asyncio
import functools
import logging
from pathlib import Path
from typing import Optional

from .metainfo import MetaInfoFile
from .protocol.peer import PeerInfo, PeerConnection
from .protocol.piece_handler import FileWriter, PieceRequester
from .tracker import TrackerManager, TrackerConnectionError, TrackerResponse, EVENT_STARTED

logger = logging.getLogger(__name__)
MAX_PEER_CONNECTIONS = 5


class DownloadError(Exception):
    pass


class Complete(Exception):
    pass


def download_complete(stop_method, stats, log):
    stop_method()
    total_time = asyncio.get_event_loop().time() - stats['started']
    log.info(f"Download stopped! Took {round(total_time, 5)}s")
    log.info(f"Downloaded: {stats['downloaded']} Uploaded: {stats['uploaded']}")
    log.info(f"Est download speed: "
             f"{round((stats['downloaded'] / total_time) / 2 ** 20, 2)} MB/s")


class Download:
    """
    A torrent currently being downloaded by the Client.
    This wraps the tracker, requester, and peer handling into a single API.
    """

    def __init__(self, torrent_fp: Path, destination: Path, local_peer: PeerInfo):
        self.client_info = local_peer
        self.torrent: MetaInfoFile = MetaInfoFile.from_file(torrent_fp, destination)
        self.stats = {"uploaded": 0, "downloaded": self.torrent.present, "left": self.torrent.remaining, "started": 0.0}
        self.tracker = TrackerManager(self.client_info, self.torrent, self.stats)
        self.peer_q = asyncio.Queue()
        self.writer = FileWriter(self.torrent)
        self.peers = []
        self.abort = False
        self.task = None
        self.download_complete_cb = functools.partial(download_complete, self.stop, self.stats, logger)
        self.requester = PieceRequester(self.torrent, self.writer, self.download_complete_cb, self.stats)

    def stop(self):
        if self.task:
            self.task.cancel()

    def download(self):
        self.torrent.check_existing_pieces()
        logger.info(f"We have: {self.torrent.present}b")
        logger.info(f"We need: {self.torrent.remaining}b")
        if self.torrent.present == self.torrent.total_size:
            raise Complete
        self.stats["started"] = asyncio.get_event_loop().time()
        self.task = asyncio.create_task(self.download_coro(), name=f"Download for {self.torrent}")
        return self.task

    def _add_peers(self, response: TrackerResponse) -> Optional[int]:
        if response:
            while not self.peer_q.empty():
                self.peer_q.get_nowait()

            for peer in response.get_peers():
                if peer[0] == self.client_info.ip and peer[1] == self.client_info.port:
                    logger.info(f"Ignoring peer. It's us...")
                    continue
                self.peer_q.put_nowait(PeerInfo(peer[0], peer[1]))
            if response.interval:
                return response.interval

    async def download_coro(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        TODO: needs work
        """
        previous = None
        interval = self.tracker.DEFAULT_INTERVAL
        self.peers = [PeerConnection(self.client_info, self.torrent.info_hash, self.requester, self.peer_q)
                      for _ in range(MAX_PEER_CONNECTIONS)]

        try:
            event = EVENT_STARTED
            while True:
                if self.requester.complete:
                    if not event:
                        await self.tracker.completed()

                if self.abort:
                    logger.info(f"Aborting download of {self.torrent.name}. Downloaded {self.stats['downloaded']} "
                                f"bytes")
                    await self.tracker.cancel()
                    break

                current = asyncio.get_running_loop().time()
                if (not previous) or (previous + interval < current):
                    try:
                        response = await self.tracker.announce(event)
                        if event:
                            event = ""
                    except TrackerConnectionError:
                        self.abort = True
                        continue

                    interval = self._add_peers(response)
                    if interval is not None:
                        previous = current
                        interval = response.interval
                else:
                    await asyncio.sleep(interval)
        except (asyncio.CancelledError, Exception) as e:
            logger.debug(f"{type(e).__name__} exception received in client.download.")
            logger.exception(e, exc_info=True)
            await self.tracker.cancel()
        finally:
            logger.debug(f"Ending download loop. Cleaning up.")
            self.download_complete_cb()
            for peer in self.peers:
                peer.stop_forever()
