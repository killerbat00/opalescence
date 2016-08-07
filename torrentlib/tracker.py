"""
Support for communication with an external tracker.
B A S I C

author: brian houston morrow
"""

import random
import types

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
        self.info_hash = torrent.info_hash
        self.announce_url = torrent.announce
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

        bencoded_resp = r.content
        try:
            decoded_obj = bdecode(bencoded_resp)
        except DecodeError as e:
            raise TrackerResponseError("Unable to decode tracker response.\n{prev_msg}".format(prev_msg=e.message))

        if "failure reason" in decoded_obj:
            raise TrackerResponseError(
                "Request to {tracker_url} failed.\n{failure_msg}".format(tracker_url=self.announce_url,
                                                                         failure_msg=decoded_obj["failure reason"]))

        interval = decoded_obj["interval"]
        mininterval = 0
        if "min interval" in decoded_obj:
            mininterval = decoded_obj["min interval"]

        if "tracker id" in decoded_obj:
            self.tracker_id = decoded_obj["tracker id"]

        complete = decoded_obj["complete"]
        incomplete = decoded_obj["incomplete"]
        peers = decoded_obj["peers"]

        return TrackerHttpResponse(interval=interval, mininterval=mininterval, tracker_id=self.tracker_id,
                                   complete=complete, incomplete=incomplete, peers=peers)

    @utils.decorators.log_this
    def make_request(self, event=tracker_event["started"]):
        params = {}
        params.setdefault("info_hash", self.info_hash)
        params.setdefault("peer_id", self.peer_id)
        params.setdefault("port", self.port)
        params.setdefault("uploaded", self.uploaded)
        params.setdefault("downloaded", self.downloaded)
        params.setdefault("left", self.left)
        params.setdefault("compact", self.compact)
        params.setdefault("no_peer_id", self.no_peer_id)
        params.setdefault("event", self.event)

        r = requests.get(self.announce_url, params=params)
        return self._decode_response(r)


class TrackerHttpResponse(object):
    def __init__(self, interval=0, mininterval=0, tracker_id="", complete=0, incomplete=0, peers=""):
        # required
        self.interval = interval
        self.mininterval = mininterval
        self.tracker_id = tracker_id
        self.complete = complete
        self.incomplete = incomplete
        # TODO: Figure out how to differentiate between a list of dictionaries and a string here
        self.peers = peers  # list of dictionaries OR byte string of length % 6 = 0

        if self.peers:
            self._decode_peers()

    def _decode_peers(self):
        if isinstance(self.peers, types.StringType):
            pass  # decode bytestring
        elif isinstance(self.peers, types.ListType):
            pass  # save peer_list
        else:
            raise TrackerResponseError("Inavlid peer list {peer_list}".format(peer_list=self.peers))
