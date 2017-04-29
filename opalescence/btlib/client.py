# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""
import asyncio
import logging

from . import log_and_raise
from .peer import Peer, PeerError
from .peer.piece_handler import Requester
from .torrent import Torrent
from .tracker import Tracker, TrackerError

logger = logging.getLogger(__name__)


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class Client:
    """
    Handles communication with the tracker and between peers
    """

    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.tracker = Tracker(self.torrent)
        self.requester = Requester(self.torrent)
        self.peer = None
        self.peer_list = []
        self.interval = self.tracker.DEFAULT_INTERVAL
        self.last_ping = 0
        self.loop = asyncio.get_event_loop()

    async def ping(self):
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
            log_and_raise(f"Unable to make announce call to {self.tracker}", logger, ClientError, te)

    def next_peer(self) -> None:
        """
        Assigns the next peer in our list as the current one with which we are communicating
        """
        if not self.peer_list:
            task = self.loop.create_task(self.ping())
            self.loop.call_soon(task)
            return

        p = self.peer_list.pop()
        self.peer = Peer(p[0], p[1], self.torrent, self.tracker.peer_id, self.requester)

    async def start(self):
        """
        Schedules the recurring announce call with the tracker.
        """
        while True:
            try:
                await self.ping()
                self.next_peer()
                await self.peer.start()
            except PeerError:
                self.requester.remove_peer(self.peer)
                self.next_peer()
                await self.peer.start()
                continue
            except ClientError as e:
                raise e
            await asyncio.sleep(self.interval)
