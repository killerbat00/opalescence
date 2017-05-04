# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""
import asyncio
import logging

from .metainfo import MetaInfoFile
from .protocol.peer import PeerError, Peer
from .protocol.piece_handler import Requester
from .tracker import Tracker, TrackerError

logger = logging.getLogger(__name__)


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class ClientTorrent:
    """
    A torrent currently being handled by the client. This wraps the tracker, requester, and peers into a single
    API.
    """

    def __init__(self, torrent: MetaInfoFile):
        self.torrent = torrent
        self.tracker = Tracker(self.torrent)
        self.requester = Requester(self.torrent)
        self.current_peers = []
        self.peer_list = []
        self.interval = self.tracker.DEFAULT_INTERVAL
        self.last_ping = 0
        self.loop = asyncio.get_event_loop()
        self.future = asyncio.ensure_future(self.start())

    async def cancel(self):
        """
        Cancels this download.
        """
        logger.debug(f"Cancelling download of {self.torrent.name}.")
        await self.tracker.cancel()
        if not self.future.done():
            self.future.cancel()

    async def _ping(self):
        """
        Pings the tracker. Called periodically based on the interval requested by the tracker.
        """
        if self.last_ping and not ((self.loop.time() - self.interval) > self.last_ping):
            return

        try:
            resp = await self.tracker.announce()
            self.last_ping = self.loop.time()

            if resp.interval:
                self.interval = resp.interval

            p = resp.peers
            if p:
                self.peer_list = p

        except TrackerError as te:
            logger.error(f"Unable to announce to {self.tracker}.")
            logger.info(te, exc_info=True)
            raise ClientError from te

    def assign_peers(self) -> None:
        """
        Assigns the first 10 peers in the peer list to the active peers.
        """
        for p in self.current_peers:
            self.requester.remove_peer(p)

        self.current_peers = []

        for x in range(10):
            p = self.peer_list.pop()
            self.current_peers.append(Peer(p[0], p[1], self.torrent, self.tracker.peer_id, self.requester))

    async def start(self):
        """
        Schedules the recurring announce call with the tracker.
        """
        while True:
            try:
                await self._ping()
                self.assign_peers()
            except PeerError:
                self.assign_peers()
                continue
            except ClientError as e:
                raise e
            await asyncio.sleep(self.interval)


class Client:
    """
    The client manages multiple client torrents.
    """

    def __init__(self):
        self.tasks = []
        self.torrents = {}

    def download(self, torrent: MetaInfoFile):
        """
        Starts downloading the torrent. Multiple torrents can be downloaded simultaneously.
        :param torrent: Torrent to download.
        """
        if torrent not in self.torrents:
            self.torrents[torrent] = ClientTorrent(torrent)

    async def stop(self, torrent: MetaInfoFile = None):
        """
        Stops downloading the specified torrent, or all torrents if none specified.
        :param torrent: torrent to stop downloading. Default = None = ALL torrents
        """
        if torrent:
            await self.torrents[torrent].cancel()
        else:
            tasks = []
            for t, ct in self.torrents.items():
                tasks.append(ct.cancel)
            asyncio.gather(*[x() for x in tasks])
