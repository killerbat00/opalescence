# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""

__all__ = ['ClientError', 'ClientTorrent']

import asyncio
import logging
from logging import getLogger
from random import randint

from .metainfo import MetaInfoFile
from .protocol.peer import PeerConnection, PeerInfo
from .protocol.piece_handler import PieceRequester, FileWriter
from .tracker import TrackerConnection, TrackerConnectionError

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
    return ("-OP0001-" + ''.join(str(randint(0, 9)) for _ in range(12))).encode("UTF-8")


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class ClientTorrent:
    """
    A torrent currently being handled by the client. This wraps the tracker, requester, and peers into a single
    API.
    """

    def __init__(self, torrent: MetaInfoFile, destination: str):
        self.client_info = PeerInfo(LOCAL_IP, LOCAL_PORT, PEER_ID)
        self.torrent = torrent
        self.stats = {"uploaded": 0, "downloaded": 0, "left": torrent.total_size, "started": 0.0}
        self.tracker = TrackerConnection(self.client_info, torrent, self.stats)
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
