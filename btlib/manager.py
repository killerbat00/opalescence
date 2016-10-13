# -*- coding: utf-8 -*-

"""
Manages torrent communication with trackers and peers

author: brian houston morrow
"""
import asyncio
import logging

from btlib.torrent import Torrent

logger = logging.getLogger('opalescence.' + __name__)


class _ManagedTorrent(Torrent):
    def __init__(self, torrent_path: str):
        self.peers = []
        t = Torrent.from_file(torrent_path)
        super().__init__(t.tracker_urls, t.files, t.name, t.base_location, comment=t.comment, created_by=t.created_by,
                         creation_date=t.creation_date, pieces=t.pieces, piece_length=t.piece_length,
                         info_hash=t.info_hash)

    def got_peers(self, peers):
        self.peers = peers
        for p in self.peers:
            asyncio.ensure_future(p.basic_comm())
        #        to_del = []
        #        for i, p in enumerate(self.peers):
        #            try:
        #                p.basic_comm()
        #            except socket.error:
        #                to_del.append(i)
        #
        #        for i in to_del:
        #            del self.peers[i]
        #        print("Tried all peers")
        #        print(self.peers)

    def start_trackers(self):
        for t in self.trackers:
            asyncio.ensure_future(t.tracker_comm(self.got_peers))


class Manager(object):
    def __init__(self, torrent_list: list):
        self.torrent_list = [_ManagedTorrent(x) for x in torrent_list]

    def start_download(self):
        torrent = self.torrent_list[0]
        torrent.start_trackers()
        # if not request:
        #    return False
        # try:
        #    return request[0].basic_comm()
        # except TimeoutError:
        #    logger.debug("Timed out connecting to {peer}".format(peer=torrent.trackers[0].peer_list[0].ip))
