# -*- coding: utf-8 -*-

"""
Contains tests for the peer functionality of btlib
"""
import asyncio
import os
from unittest import TestCase

from requests import get

from tests.context import torrent, tracker, peer
from tests.utils import async_run


class TestPeer(TestCase):
    """
    Tests the peer model used to communicate with peers
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = "http://releases.ubuntu.com/16.04/ubuntu-16.04.2-desktop-amd64.iso.torrent"
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
        cls.torrent = torrent.Torrent.from_file(cls.external_torrent_path)
        cls.tracker = tracker.Tracker(cls.torrent)

    @classmethod
    def tearDownClass(cls):
        """
        Closes the tracker's http client session
        """
        cls.tracker.close()

    def test_basic_comm(self):
        """
        """
        resp = async_run(self.tracker.announce())
        peers = resp.peers

        for p in peers:
            pp = peer.Peer(p[0], p[1], self.torrent.info_hash, self.tracker.peer_id)
            try:
                async_run(asyncio.wait_for(pp._start(), 5.0))
            except asyncio.futures.TimeoutError:
                print("TimeoutError")
                continue
            except OSError:
                print("OSError")
                continue
