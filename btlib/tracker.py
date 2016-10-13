# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
B A S I C

author: brian houston morrow
"""

import asyncio
import logging
import random
import socket
import struct

import aiohttp

from .bencode import bdecode, DecodeError
from .peer import Peer

logger = logging.getLogger('opalescence.' + __name__)


class TrackerError(Exception):
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

    def __init__(self, url: str, info_hash: str, total_size: int, port: int = 6881):
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
        self.peer_list = set()

        # optional
        self.tracker_id = ""
        self.ip = None
        self.numwant = 10  # Default to asking for 10 peers
        self.key = None

        # response
        self.interval = 2
        self.mininterval = 0
        self.seeders = 0
        self.leechers = 0
        self.peers = ""  # list of dictionaries OR byte string of length % 6 = 0

    def _decode_peers(self) -> None:
        """
        Decodes the peer list from a list of OrderedDict or a string of bytes into a list of ip:port
        TODO: Improve this a bit - it's probably not a great idea to read from self.peers then immediately overwrite it
              after decoding.
              I'm also not confident in how the ip addresses and ports are handled.
              peer id handling is also wrong, but not affected for the test torrent i'm using now
        """
        peers = []

        logger.debug("Decoding peer list received from: {url}".format(url=self.announce_url))

        # bytestring response from tracker
        if isinstance(self.peers, str):
            peer_len = len(self.peers)
            if peer_len % 6 != 0:
                logger.debug("Invalid peer list. Length {length} should be a multiple of 6.".format(length=peer_len))
                raise TrackerError

            for i in range(0, peer_len - 1, 6):
                peer_bytes = self.peers[i:i + 6]
                ip_bytes = struct.unpack("!L", peer_bytes[0:4].encode("ISO-8859-1"))[0]
                ip = socket.inet_ntoa(struct.pack('!L', ip_bytes))
                port = struct.unpack("!H", peer_bytes[4:6].encode("ISO-8859-1"))[0]
                peers.append(str(ip) + ":" + str(port))

        # this part is untested - dictionary response
        # elif isinstance(self.peers, list):
        #    for peer in self.peers:
        #        assert (isinstance(peer, dict))

        #        if ["ip", "port", "peer id"] not in peer:
        #            raise TrackerError("Invalid peer list. Unable to decode {peer}".format(peer=peer))
        #        peers.append([peer.get("ip"), peer.get("port")])
        #        self.peer_list.add(Peer(peer.get("ip"), peer.get("port"), self.info_hash, self.peer_id))
        else:
            logger.debug("Invalid peer list {peer_list}".format(peer_list=self.peers))
            raise TrackerError

        peers = set(peers)
        self.peer_list = [Peer(x.split(":")[0], x.split(":")[1], self.info_hash, self.peer_id) for x in peers]
        return self.peer_list

    async def _decode_response(self, r: aiohttp.ClientResponse) -> None:
        """
        Decodes the content of a requests.Response response to the tracker
        :param r:   requests.Response to the request we made to the tracker
        :return:    TrackerHttpResponse object, raises TrackerResponseError if anything goes wrong
        """
        # type (requests.Response) -> None
        assert (isinstance(r, aiohttp.ClientResponse))

        logger.debug("Debugging tracker response from: {url}".format(url=self.announce_url))

        bencoded_resp = await r.read()
        try:
            decoded_obj = bdecode(bencoded_resp)
        except DecodeError as e:
            logger.debug("Unable to decode tracker response.\n{prev_msg}".format(prev_msg=e))
            raise TrackerError from e

        if "failure reason" in decoded_obj:
            logger.debug("Request to {tracker_url} failed.\n{failure_msg}".format(tracker_url=self.announce_url,
                                                                                  failure_msg=decoded_obj[
                                                                                      "failure reason"]))
            raise TrackerError

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

    async def make_request(self, event=EventEnum.started):
        """
        Makes a request to the tracker notifying it of our current stats.
        :param client:  aiohttp client session
        :param event:   optional,defaults to Started - One of Started, Stopped, Completed
                        to let the tracker know our current status
        :return:        True if response was received and Info updated, else False
        """
        if event != self.event:
            self.event = event

        loop = asyncio.get_event_loop()

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

        logger.debug("Making request to tracker: {url}".format(url=self.announce_url))
        async with aiohttp.ClientSession(loop=loop) as client:
            async with client.get(self.announce_url, params=params) as r:
                if r.status == 200:
                    logger.debug("Request successful to: {url}".format(url=self.announce_url))
                    try:
                        return await self._decode_response(r)
                    except TrackerError as te:
                        logger.debug("Unable to decode tracker response.")
                        raise TrackerError from te
                else:
                    logger.debug("Request unsuccessful.")
                    raise TrackerError

    async def tracker_comm(self, cb):
        await asyncio.ensure_future(self.make_request())
        cb(self.peer_list)
        await asyncio.sleep()
        asyncio.ensure_future(self.tracker_comm(cb))
