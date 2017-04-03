# -*- coding: utf-8 -*-

"""
Contains tests for the peer functionality of btlib
"""
import os
from unittest import TestCase

from requests import get

from tests.context import torrent, tracker


class TestPeer(TestCase):
    """
    Tests the peer model used to communicate with peers
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = "http://releases.ubuntu.com/16.04/ubuntu-16.04.2-desktop-amd64.iso.torrent"

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

    def test_basic_comm(self):
        """
        """
        self.fail()
