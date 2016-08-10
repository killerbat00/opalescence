"""
Support for communication with an external tracker.
B A S I C

author: brian houston morrow
"""

import random
import socket
import struct
import types

import requests

from bencode import bdecode, DecodeError
from peer import Peer


class TrackerCommError(Exception):
    """
    Raised when we encounter an error while communicating with the tracker.
    """
    pass


class EventEnum(object):
    """
    type used for more easily handling the tracker's event
    """
    started = 0
    completed = 1
    stopped = 2


class TrackerInfo(object):
    """
    Represents the info from the tracker for a given torrent, providing methods
    to schedule the information to refresh
    """

    def __init__(self, url, info_hash, total_size, port=6881):
        # required
        self.info_hash = info_hash
        self.announce_url = url
        self.peer_id = "-OP0020-" + str(random.randint(100000000000, 999999999999))
        self.port = port
        self.uploaded = 0
        self.downloaded = 0
        self.left = total_size
        self.compact = 0
        self.no_peer_id = 0
        self.event = EventEnum.started
        self.peer_list = []

        # optional
        self.tracker_id = ""
        self.ip = None
        self.numwant = 50  # Default to asking for 30 peers
        self.key = None

        # response
        self.interval = 0
        self.mininterval = 0
        self.seeders = 0
        self.leechers = 0
        self.peers = ""  # list of dictionaries OR byte string of length % 6 = 0

    def _decode_peers(self):
        """
        Decodes the peer list from a list of OrderedDict or a string of bytes into a list of ip:port
        TODO: Improve this a bit - it's probably not a great idea to read from self.peers then immediately overwrite it
              after decoding.
              I'm also not confident in how the ip addresses and ports are handled.
              peer id handling is also wrong, but not affected for the test torrent i'm using now
        """
        if isinstance(self.peers, types.StringType):
            peer_len = len(self.peers)
            if peer_len % 6 != 0:
                raise TrackerCommError(
                    "Invalid peer list. Length {length} should be a multiple of 6.".format(length=peer_len))

            for i in range(0, peer_len - 1, 6):
                peer_bytes = self.peers[i:i + 6]
                ip_bytes = struct.unpack("!L", peer_bytes[0:4])[0]
                ip = socket.inet_ntoa(struct.pack('!L', ip_bytes))
                port = struct.unpack("!H", peer_bytes[4:6])[0]
                self.peer_list.append(Peer(ip, port, self.info_hash, self.peer_id))
        # this part is untested
        elif isinstance(self.peers, types.ListType):
            for peer in self.peers:
                assert (isinstance(peer, types.DictionaryType))

                if ["ip", "port", "peer id"] not in peer:
                    raise TrackerCommError("Invalid peer list. Unable to decode {peer}".format(peer=peer))
                self.peer_list.append(Peer(peer.get("ip"), peer.get("port"), self.info_hash, self.peer_id))
        else:
            raise TrackerCommError("Invalid peer list {peer_list}".format(peer_list=self.peers))

    def _decode_response(self, r):
        """
        Decodes the content of a requests.Response response to the tracker
        :param r:   requests.Response to the request we made to the tracker
        :return:    TrackerHttpResponse object, raises TrackerResponseError if anything goes wrong
        """
        # type (requests.Response) -> None
        assert (isinstance(r, requests.Response))

        bencoded_resp = r.content
        try:
            decoded_obj = bdecode(bencoded_resp)
        except DecodeError as e:
            raise TrackerCommError("Unable to decode tracker response.\n{prev_msg}".format(prev_msg=e.message))

        if "failure reason" in decoded_obj:
            raise TrackerCommError(
                "Request to {tracker_url} failed.\n{failure_msg}".format(tracker_url=self.announce_url,
                                                                         failure_msg=decoded_obj["failure reason"]))

        self.interval = decoded_obj["interval"]
        if "min interval" in decoded_obj:
            self.mininterval = decoded_obj["min interval"]

        if "tracker id" in decoded_obj:
            self.tracker_id = decoded_obj["tracker id"]

        self.seeders = decoded_obj["complete"]
        self.leechers = decoded_obj["incomplete"]
        self.peers = decoded_obj["peers"]
        self._decode_peers()

        # after this we'll be making regular requests to the tracker so we don't need to specify this
        # until we encounter another event
        if self.event and self.event is EventEnum.started:
            self.event = None

    def make_request(self, event=EventEnum.started):
        """
        Makes a request to the tracker notifying it of our curent stats.
        :param event:   optional,defaults to Started - One of Started, Stopped, Completed
                        to let the tracker know our current status
        :return:        True if response was received and Info updated, else False
        """
        if event != self.event:
            self.event = event

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
        params.setdefault("numwant", self.numwant)

        r = requests.get(self.announce_url, params=params)
        if r.status_code == 200:
            self._decode_response(r)
            return True
        return False
