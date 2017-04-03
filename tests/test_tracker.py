#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tests functionality related to opalescence's handling of tracker requests and responses.
asyncio testing methodology via miguel grinberg (https://blog.miguelgrinberg.com/post/unit-testing-asyncio-code)
"""
import asyncio
import os
import socket
import struct
from copy import copy
from unittest import TestCase, mock

from requests import get

from tests.context import torrent
from tests.context import tracker


def _run(coro):
    """
    runs the specified asynchronous coroutine once in an event loop

    :param coro: coroutine to run
    :return:     the result of the coroutine
    """
    return asyncio.get_event_loop().run_until_complete(coro)


def create_async_mock(data: bytes, status: int):
    """
    Creates a MagicMock function object that will behaves like an async coroutine and that can be used
    to replace a function used in an async with statement
    :param data:   data that will be returned when the mock connection is read
    :param status: the mock connection's status
    """

    class AsyncMock(mock.MagicMock):
        """
        Mock class that works with an async context manager. Currently used to mock aiohttp.ClientSession.get
        the ClientResponse is a MagicMock with the specified data and status.
        """

        async def __aenter__(self):
            conn = mock.MagicMock()
            f = asyncio.Future()
            f.set_result(data)
            conn.read = mock.MagicMock(return_value=f)
            type(conn).status = mock.PropertyMock(return_value=status)
            return conn

        async def __aexit__(self, *_):
            pass

    return AsyncMock()


class TestTracker(TestCase):
    """
    Tests the request to the tracker.
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = "http://releases.ubuntu.com/16.04/ubuntu-16.04.2-desktop-amd64.iso.torrent"

    @classmethod
    def setUpClass(cls):
        """
        Downloads an ubuntu torrent to use for testing.
        """
        cls.external_torrent_path = os.path.join(cls.external_torrent_path, cls.torrent_url.split("/")[-1])
        r = get(cls.torrent_url)
        if r.status_code == 200:
            file_data = r.content
            with open(cls.external_torrent_path, "wb+") as f:
                f.write(file_data)
        cls.torrent = torrent.Torrent.from_file(cls.external_torrent_path)

    @classmethod
    def tearDownClass(cls):
        """
        Removes the test data directory created for testing.
        """
        if os.path.exists(cls.external_torrent_path):
            os.remove(cls.external_torrent_path)

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

    def test_announce(self):
        """
        Tests the announce method of a tracker
        """
        t = tracker.Tracker(self.torrent)
        resp = _run(t.announce())
        self.assertIsInstance(resp, tracker.Response)
        t.close()

    def test_invalid_request(self):
        """
        Tests that announce fails with an invalid request
        """
        t = copy(self.torrent)
        t.meta_info[b"announce"] = b"invalid announce"
        track = tracker.Tracker(t)
        with self.subTest(msg="Invalid URL"):
            self.assertRaises(ValueError, _run, track.announce())
        track.close()
        t.meta_info[b"announce"] = b"http://httpstat.us/404"
        track = tracker.Tracker(t)
        with self.subTest(msg="Bogus URL"):
            self.assertRaises(tracker.TrackerCommError, _run, track.announce())
        track.close()

    def test_invalid_params(self):
        """
        Tests that a TrackerCommError is thrown when we send the tracker inavlid parameters
        """
        track = tracker.Tracker(self.torrent)
        track._make_params = mock.MagicMock(return_value={})
        with self.subTest(msg="empty params"):
            self.assertRaises(tracker.TrackerCommError, _run, track.announce())
        track.close()

    def test_valid_request_bad_data(self):
        """
        Tests that a request to a page that returns a non bencoded
        dictionary throws a TrackerCommError (from a DecodeError)
        """
        t = copy(self.torrent)
        t.meta_info[b"announce"] = b"http://httpstat.us/200"
        track = tracker.Tracker(t)
        with self.subTest(msg="Valid 200 status, invalid data"):
            self.assertRaises(tracker.TrackerCommError, _run, track.announce())
        track.close()

    def test_failed_response(self):
        """
        Tests that a tracker response that failed (contains b"failure reason") throws a TrackerCommError
        """
        with self.subTest(msg="Failure reason key"):
            data = b"d14:failure reason14:mock mock mocke"
            status = 200
            with mock.patch("aiohttp.ClientSession.get", new_callable=create_async_mock(data, status)) as mocked_get:
                track = tracker.Tracker(self.torrent)
                with self.assertRaises(tracker.TrackerCommError):
                    _run(track.announce())
                track.close()
                mocked_get.assert_called_once()
                mocked_get.assert_called_with(track._make_url())


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
        tests we correctly decode the dictionary model peer response from the tracker.
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
        tests we correctly decode the bytestring peer response from the tracker
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
