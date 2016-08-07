"""
Support for communication with an external tracker.
B A S I C

author: brian houston morrow
"""

import random

import requests

import utils.decorators
from bencode import bdecode, DecodeError
from torrent import Torrent

tracker_event = {"started": 0, "completed": 1, "stopped": 2}


class TrackerResponseError(Exception):
    pass


class TrackerHttpRequest(object):
    """
    Represents a basic HTTP request to the tracker for a specified Torrent
    """

    @utils.decorators.log_this
    def __init__(self, torrent, port=666):
        # type (Torrent, int) -> TrackerHttpRequest
        """
        Creates an HTTP request to the tracker based on the info specified in a given Torrent.
        This is probably horribly inefficient and to OO; I likely don't need to keep a reference to
        the torrent object in each request
        :param torrent:     torrent from which to create request
        :param port:        port to list on, defaults to 666 (lol)
        """
        assert (isinstance(torrent, Torrent))

        # required
        self.torrent = torrent
        self.info_hash = torrent.info_hash
        self.peer_id = "-OP0020-" + str(random.randint(100000000000, 999999999999))
        self.port = port
        self.uploaded = 0
        self.downloaded = 0
        self.left = torrent.total_file_size()
        self.compact = 0
        self.no_peer_id = 0
        self.event = tracker_event["started"]
        self.tracker_id = ""

        # optional
        self.ip = None
        self.numwant = None
        self.key = None
        self.trackerid = None

    @utils.decorators.log_this
    def _decode_response(self, r):
        """
        Decodes the text of a requests.Response response to the tracker into a TrackerHttpResponse object
        :param r:   requests.Response object
        :return:    TrackerHttpResponse object, raises TrackerResponseError if anything goes wrong
        """

        # type (requests.Response) -> N
        assert (isinstance(r, requests.Response))

        bencoded_resp = r.text
        try:
            decoded_obj = bdecode(bencoded_resp)
        except DecodeError as e:
            raise TrackerResponseError("Unable to decode tracker response.\n{prev_msg}".format(prev_msg=e.message))

        if "failure reason" in decoded_obj:
            raise TrackerResponseError(
                "Request failed.\n{failure_msg}".format(failure_msg=decoded_obj["failure reason"]))

        interval = int(decoded_obj["interval"])
        mininterval = 0
        if "min interval" in decoded_obj:
            mininterval = int(decoded_obj["min interval"])

        if "tracker id" in decoded_obj:
            self.tracker_id = decoded_obj["tracker id"]

        complete = int(decoded_obj["complete"])
        incomplete = int(decoded_obj["incomplete"])
        peers = decoded_obj["peers"]

        resp = TrackerHttpResponse()
        resp.interval = interval

        if mininterval:
            resp.mininterval = mininterval

        resp.tracker_id = self.tracker_id
        resp.complete = complete
        resp.incomplete = incomplete
        resp.peers = peers

        return resp

    @utils.decorators.log_this
    def build_request(self):
        pass


class TrackerHttpResponse(object):
    def __init__(self):
        # required
        self.interval = 0
        self.mininterval = 0
        self.tracker_id = ""
        self.complete = 0
        self.incomplete = 0
        self.peers = []  # list of dictionaries


class Tracker(object):
    pass


class Comm(object):
    pass
