"""
Support for communication with an external tracker.
B A S I C

author: brian houston morrow
"""

import random

import utils.decorators
from torrent import Torrent

tracker_event = {"started": 0, "completed": 1, "stopped": 2}


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

        # optional
        self.ip = None
        self.numwant = None
        self.key = None
        self.trackerid = None

    @utils.decorators.log_this
    def build_request(self):
        pass


class Tracker(object):
    pass


class Comm(object):
    pass
