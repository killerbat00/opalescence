# -*- coding: utf-8 -*-

"""
Manages torrent communication with trackers and peers

author: brian houston morrow
"""
import asyncio
import logging

from btlib.peer import Peer
from btlib.torrent import Torrent
from btlib.tracker import Tracker

logger = logging.getLogger('opalescence.' + __name__)


class ManagedTorrent:
    def __init__(self, torrent: Torrent):
        self.tracker = Tracker(torrent)
        self.peers = []

    async def start(self):
        event = 'started'
        while True:
            response = await self.tracker.make_request(event)
            if response:
                self._empty_peer_queue()
                self.peers = [Peer(x[0], x[1], self.tracker.torrent.info_hash, self.tracker.peer_id) for x in
                              response.peers]
            #                for peer in response.peers:
            #                    self.peers.put_nowait(peer)
            await asyncio.sleep(response.interval)

    def _empty_peer_queue(self):
        pass


# while not self.peers.empty():
#            self.peers.get_nowait()


class Manager:
    def __init__(self, torrent: Torrent):
        self.torrent = ManagedTorrent(torrent)

    async def start_download(self):
        await self.torrent.start()
