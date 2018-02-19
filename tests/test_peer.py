# -*- coding: utf-8 -*-

"""
Contains tests for the protocol functionality of btlib
"""
import os
from unittest import TestCase
from unittest import skip

from requests import get

import opalescence.btlib.protocol.peer
from tests.context import metainfo, tracker, torrent_url
from tests.utils import async_run


class TestPeer(TestCase):
    """
    Tests the protocol model used to communicate with peers
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = torrent_url
    tracker = None

    @classmethod
    def setUpClass(cls):
        """
        Downloads an ubuntu torrent to use for testing.
        """
        cls.external_torrent_path = os.path.join(cls.external_torrent_path, cls.torrent_url.split("/")[-1])
        if not os.path.exists(cls.external_torrent_path):
            r = get(cls.torrent_url)
            if r.status_code == 200:
                file_data = r.content
                with open(cls.external_torrent_path, "wb+") as f:
                    f.write(file_data)
        cls.torrent = metainfo.MetaInfoFile.from_file(cls.external_torrent_path)
        cls.tracker = tracker.Tracker(cls.torrent)

    @classmethod
    def tearDownClass(cls):
        """
        Closes the tracker's http client session
        """
        cls.tracker.close()

    @skip
    def test_basic_comm(self):
        """
        """
        resp = async_run(self.tracker.announce())
        peers = resp.peers

        for p in peers:
            pp = opalescence.btlib.protocol.peer.Peer(p[0], p[1], self.torrent.info_hash, self.tracker.peer_id)
            try:
                async_run(pp.start())
            except opalescence.btlib.protocol.peer.PeerError:
                print("OSError")
                continue

    def test_handshake(self):
        """
        Tests that we can negotiate a handshake with a remote protocol.
        """
