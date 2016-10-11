# -*- coding: utf-8 -*-

"""
Manages torrent communication with trackers and peers

author: brian houston morrow
"""
import asyncio
import logging

from btlib.torrent import Torrent

logger = logging.getLogger('opalescence.' + __name__)


class _ManagedTorrent(object):
    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.trackers = torrent.trackers

    async def tracker_comm(self):
        while True:
            coros = [tracker.make_request() for tracker in self.trackers]

        yield from asyncio.gather(*coros)
        for tracker in self.trackers:
            while True:

        pass


class Manager(object):
    def __init__(self, torrent_list: list):
        self.torrent_list = [_ManagedTorrent(x) for x in torrent_list]

    async def start_download(self):
        torrent = self.torrent_list[0]
        request = await torrent.trackers[0].make_request()
        if not request:
            return False
        try:
            return await torrent.trackers[0].peer_list[0].basic_comm()
        except TimeoutError:
            logger.debug("Timed out connecting to {peer}".format(peer=torrent.trackers[0].peer_list[0].url))
