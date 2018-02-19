#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests functionality related to opalescence's handling of tracker requests and responses.
asyncio testing methodology via miguel grinberg (https://blog.miguelgrinberg.com/post/unit-testing-asyncio-code)
"""
import os
import socket
import struct
from unittest import TestCase, mock
from urllib.parse import urlencode

from requests import get

from tests.context import metainfo, tracker, torrent_url
from tests.utils import async_run, create_async_mock


class TestTracker(TestCase):
    """
    Tests the request to the tracker.
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = torrent_url

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

    def test_creation(self):
        """
        Tests we can create tracker object from a torrent
        """
        tt = tracker.Tracker(self.torrent)
        self.assertIsInstance(tt, tracker.Tracker)
        self.assertEqual(tt.torrent, self.torrent)
        self.assertEqual(len(tt.peer_id), 20)
        tt.close()

    def test__make_params(self):
        """
        tests we properly construct the parameters for the announce call
        """
        expected_params = {"info_hash": self.torrent.info_hash,
                           "port": 6881,
                           "uploaded": 0,
                           "downloaded": 0,
                           "left": 0,
                           "compact": 1,
                           "event": "started"}
        tt = tracker.Tracker(self.torrent)
        expected_params["peer_id"] = tt.peer_id
        self.assertDictEqual(tt._make_params(), expected_params)
        tt.close()

    def test__make_url(self):
        """
        tests that we properly construct the url for the announce call
        """
        tt = tracker.Tracker(self.torrent)
        expected_url = "http://torrent.ubuntu.com:6969/announce?" + urlencode(tt._make_params())
        self.assertEqual(tt._make_url(), expected_url)
        tt.close()

    def test_announce(self):
        """
        Tests the announce method of a tracker
        """
        t = tracker.Tracker(self.torrent)
        resp = async_run(t.announce())
        self.assertIsInstance(resp, tracker.Response)
        self.assertFalse(resp.failed)
        t.close()

    def test_cancel(self):
        """
        Tests the cancel announce call to the tracker
        """
        t = tracker.Tracker(self.torrent)
        t.announce = create_async_mock()
        async_run(t.cancel())
        self.assertEqual(t.event, "stopped")
        t.announce.assert_called_once()

    def test_completed(self):
        """
        Tests the completed announce call to the tracker
        """
        t = tracker.Tracker(self.torrent)
        t.announce = create_async_mock()
        async_run(t.completed())
        self.assertEqual(t.event, "completed")
        t.announce.assert_called_once()

    def test_invalid_request(self):
        """
        Tests that announce fails with an invalid request
        """
        track = tracker.Tracker(self.torrent)
        track._make_url = mock.MagicMock(return_value="malformed url")
        with self.subTest(msg="Malformed URL"):
            self.assertRaises(ValueError, async_run, track.announce())
        track.close()

        track = tracker.Tracker(self.torrent)
        with mock.patch("aiohttp.ClientSession.get",
                        new_callable=create_async_mock(data=b"", status=404)) as mocked_get:
            with self.subTest(msg="Non 200 HTTP response"):
                self.assertRaises(tracker.TrackerError, async_run, track.announce())
                mocked_get.assert_called_once()
                mocked_get.assert_called_once_with(track._make_url())

        track.close()

    def test_invalid_params(self):
        """
        Tests that a TrackerError is thrown when we send the tracker invalid parameters
        """
        track = tracker.Tracker(self.torrent)
        track._make_params = mock.MagicMock(return_value={})
        with self.subTest(msg="Empty params"):
            self.assertRaises(tracker.TrackerError, async_run, track.announce())
        track.close()

    def test_valid_request_bad_data(self):
        """
        Tests that a request to a page that returns a non bencoded
        dictionary log_and_raise a TrackerError (from a DecodeError)
        """
        data = b"Not bencoded."
        code = 200
        track = tracker.Tracker(self.torrent)
        with mock.patch("aiohttp.ClientSession.get",
                        new_callable=create_async_mock(data=data, status=code)) as mocked_get:
            with self.subTest(msg="Valid 200 HTTP response, invalid data."):
                self.assertRaises(tracker.TrackerError, async_run, track.announce())
                mocked_get.assert_called_once()
                mocked_get.assert_called_once_with(track._make_url())
        track.close()

    def test_failed_response(self):
        """
        Tests that a tracker response that failed (contains b"failure reason") log_and_raise a TrackerError
        and properly finds the failure reason
        """
        data = b"d14:failure reason14:mock mock mocke"
        status = 200
        track = tracker.Tracker(self.torrent)
        with self.subTest(msg="Failure reason key"):
            with mock.patch("aiohttp.ClientSession.get",
                            new_callable=create_async_mock(data=data, status=status)) as mocked_get:
                with self.assertRaises(tracker.TrackerError):
                    async_run(track.announce())
                mocked_get.assert_called_once()
                mocked_get.assert_called_with(track._make_url())
        track.close()


class TestResponse(TestCase):
    """
    Tests the tracker's response to our request.
    """

    def test_creation(self):
        """
        tests response creation
        """
        r = tracker.Response(dict())
        self.assertIsInstance(r, tracker.Response)
        self.assertEqual(r.data, dict())
        self.assertEqual(r.failure_reason, None)

    def test_failure(self):
        """
        tests a failed response identifies itself properly
        """
        fail_dict = {b"failure reason": b"reason"}
        r = tracker.Response(fail_dict)
        self.assertTrue(r.failed)
        self.assertEqual(r.failure_reason, "reason")

    def test_peer_dict(self):
        """
        tests we correctly decode the dictionary model protocol response from the tracker.
        """
        dictionary_peers = {b"peers": [{b"ip": b"127.0.0.1", b"port": 6969},
                                       {b"ip": b"0.0.0.0", b"port": 1}]}
        peer_list = [("127.0.0.1", 6969), ("0.0.0.0", 1)]
        r = tracker.Response(dictionary_peers)
        peers = r.peers
        for p in peers:
            self.assertIn(p, peer_list)

    def test_peer_string(self):
        """
        tests we correctly decode the bytestring protocol response from the tracker
        """
        ip1 = socket.inet_aton("127.0.0.1")
        p1 = struct.pack(">H", 6969)
        ip2 = socket.inet_aton("0.0.0.0")
        p2 = struct.pack(">H", 1)
        peer_bytes = b"%(ip1)s%(p1)s%(ip2)s%(p2)s" % {b"ip1": ip1, b"p1": p1, b"ip2": ip2, b"p2": p2}
        resp_dict = {b"peers": peer_bytes}
        peer_list = [("127.0.0.1", 6969), ("0.0.0.0", 1)]
        r = tracker.Response(resp_dict)
        peers = r.peers
        for p in peers:
            self.assertIn(p, peer_list)
