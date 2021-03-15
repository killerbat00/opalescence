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

from requests import get

from opalescence.btlib import metainfo, tracker as tracker
from tests.context import torrent_url
from tests.utils import async_run, create_async_mock


class TestTracker(TestCase):
    """
    Tests the request to the tracker.
    """
    external_torrent_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), torrent_url.split("/")[-1])

    @classmethod
    def setUpClass(cls):
        """
        Downloads an ubuntu torrent to use for testing.
        """
        if not os.path.exists(cls.external_torrent_path):
            r = get(torrent_url)
            if r.status_code == 200:
                file_data = r.content
                with open(cls.external_torrent_path, "wb+") as f:
                    f.write(file_data)
        cls.torrent: metainfo.MetaInfoFile = metainfo.MetaInfoFile.from_file(cls.external_torrent_path)

    def test_creation(self):
        """
        Tests we can create tracker object from a torrent
        """
        tt = tracker.TrackerConnection(b"fake", self.torrent)
        self.assertIsInstance(tt, tracker.TrackerConnection)
        self.assertEqual(tt.info_hash, self.torrent.info_hash)
        self.assertEqual(tt.announce_urls, self.torrent.announce_urls)
        self.assertEqual(tt.peer_id, b"fake")

    def test__make_params(self):
        """
        tests we properly construct the parameters for the announce call
        """
        expected_params = {"info_hash": self.torrent.info_hash,
                           "peer_id": b"fake",
                           "port": 6881,
                           "uploaded": 0,
                           "downloaded": 0,
                           "left": 958398464,
                           "compact": 1,
                           "event": tracker.EVENT_STARTED}
        tt = tracker.TrackerConnection(b"fake", self.torrent)
        self.assertEqual(expected_params, tt._get_url_params(tracker.EVENT_STARTED))

    def test_announce(self):
        """
        Tests the announce method of a tracker
        """
        t = tracker.TrackerConnection(b"-bM0100-010293949201", self.torrent)
        resp = async_run(t.announce())
        self.assertIsInstance(resp, tracker.Response)
        self.assertFalse(resp.failed)
        async_run(t.http_client.close())

    def test_cancel(self):
        """
        Tests the cancel announce call to the tracker
        """
        t = tracker.TrackerConnection(b"fake", self.torrent)
        t.announce = create_async_mock()
        async_run(t.cancel())
        t.announce.assert_called_once_with(event=tracker.EVENT_STOPPED)
        async_run(t.http_client.close())

    def test_completed(self):
        """
        Tests the completed announce call to the tracker
        """
        t = tracker.TrackerConnection(b"fake", self.torrent)
        t.announce = create_async_mock()
        async_run(t.completed())
        t.announce.assert_called_once_with(event=tracker.EVENT_COMPLETED)
        async_run(t.http_client.close())

    def test_invalid_request(self):
        """
        Tests that announce fails with an invalid request
        """
        track = tracker.TrackerConnection(b"fake", self.torrent)
        track._get_url_params = mock.MagicMock(return_value=[])
        with self.subTest(msg="Malformed URL"):
            self.assertRaises(tracker.TrackerConnectionError, async_run, track.announce())
        async_run(track.http_client.close())

        track = tracker.TrackerConnection(b"fake", self.torrent)
        with mock.patch("aiohttp.ClientSession.get",
                        new_callable=create_async_mock(data=b"", status=404)) as mocked_get:
            with self.subTest(msg="Non 200 HTTP response"):
                self.assertRaises(tracker.TrackerConnectionError, async_run, track.announce())
                mocked_get.assert_called_once()
        async_run(track.http_client.close())

    def test_invalid_params(self):
        """
        Tests that a TrackerError is thrown when we send the tracker invalid parameters
        """
        track = tracker.TrackerConnection(b"fake", self.torrent)
        track._get_url_params = mock.MagicMock(return_value={})
        with self.subTest(msg="Empty params"):
            self.assertRaises(tracker.TrackerConnectionError, async_run, track.announce())
        async_run(track.http_client.close())

    def test_valid_request_bad_data(self):
        """
        Tests that a request to a page that returns a non bencoded
        dictionary log_and_raise a TrackerError (from a DecodeError)
        """
        data = b"Not bencoded."
        code = 200
        track = tracker.TrackerConnection(b"fake", self.torrent)
        with mock.patch("aiohttp.ClientSession.get",
                        new_callable=create_async_mock(data=data, status=code)) as mocked_get:
            with self.subTest(msg="Valid 200 HTTP response, invalid data."):
                self.assertRaises(tracker.TrackerConnectionError, async_run, track.announce())
                mocked_get.assert_called_once()
        async_run(track.http_client.close())

    def test_failed_response(self):
        """
        Tests that a tracker response that failed (contains b"failure reason") log_and_raise a TrackerError
        and properly finds the failure reason
        """
        data = b"d14:failure reason14:mock mock mocke"
        status = 200
        track = tracker.TrackerConnection(b"fake", self.torrent)
        with self.subTest(msg="Failure reason key"):
            with mock.patch("aiohttp.ClientSession.get",
                            new_callable=create_async_mock(data=data, status=status)) as mocked_get:
                with self.assertRaises(tracker.TrackerConnectionError):
                    async_run(track.announce())
                mocked_get.assert_called_once()
        async_run(track.http_client.close())


class TestResponse(TestCase):
    """
    Tests the tracker's response to our request.
    """

    def test_valid_creation(self):
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
        fail_dict = {"failure reason": b"reason"}
        r = tracker.Response(fail_dict)
        self.assertTrue(r.failed)
        self.assertEqual(r.failure_reason, "reason")

    def test_peer_dict(self):
        """
        tests we correctly decode the dictionary model peer response from the tracker.
        """
        dictionary_peers = {"peers": [{"ip": b"127.0.0.1", "port": 6969},
                                      {"ip": b"0.0.0.0", "port": 1}]}
        peer_list = [("127.0.0.1", 6969), ("0.0.0.0", 1)]
        r = tracker.Response(dictionary_peers)
        peers = r.get_peers()
        for p in peers:
            self.assertIn(p, peer_list)

    def test_compact_peer_string(self):
        """
        tests we correctly decode the bytestring peer response from the tracker
        """
        ip1 = socket.inet_aton("127.0.0.1")
        p1 = struct.pack(">H", 6969)
        ip2 = socket.inet_aton("0.0.0.0")
        p2 = struct.pack(">H", 1)
        peer_bytes = b"%(ip1)s%(p1)s%(ip2)s%(p2)s" % {b"ip1": ip1, b"p1": p1, b"ip2": ip2, b"p2": p2}
        resp_dict = {"peers": peer_bytes}
        peer_list = [("127.0.0.1", 6969), ("0.0.0.0", 1)]
        r = tracker.Response(resp_dict)
        peers = r.get_peers()
        for p in peers:
            self.assertIn(p, peer_list)

    def test_invalid_peer_string(self):
        """
        tests we correctly reject an unknown peer response from the tracker
        """
        with self.subTest(msg="Empty dict."):
            self.assertIsNone(tracker.Response({}).get_peers())
        with self.subTest(msg="Key with empty value in dict."):
            self.assertIsNone(tracker.Response({"peers": ""}).get_peers())

        with self.assertRaises(tracker.TrackerConnectionError):
            resp_dict = {"peers": "not a dict or bytestring"}
            tracker.Response(resp_dict).get_peers()

    def test_interval(self):
        """
        tests we respect the min interval and default intervals.
        """
        with self.subTest(msg="No interval specified."):
            default = tracker.TrackerConnection.DEFAULT_INTERVAL
            self.assertEqual(default, tracker.Response({}).interval)
        with self.subTest(msg="Only interval specified."):
            interval = 55
            self.assertEqual(interval, tracker.Response({"interval": interval}).interval)
        with self.subTest(msg="Only min interval, lower than default."):
            min_interval = 5
            self.assertEqual(min_interval, tracker.Response({"min interval": min_interval}).interval)
        with self.subTest(msg="Only min interval, higher than default."):
            min_interval = 105
            self.assertEqual(tracker.TrackerConnection.DEFAULT_INTERVAL,
                             tracker.Response({"min interval": min_interval}).interval)
        with self.subTest(msg="Lower min interval."):
            min_interval = 5
            interval = 55
            self.assertEqual(min_interval, tracker.Response({"min interval": min_interval,
                                                             "interval": interval}).interval)
        with self.subTest(msg="Lower interval."):
            min_interval = 55
            interval = 5
            self.assertEqual(interval, tracker.Response({"min interval": min_interval,
                                                         "interval": interval}).interval)
