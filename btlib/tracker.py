# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.

author: brian houston morrow
"""

import logging
import random
import socket
import struct

import aiohttp

from .bencode import bdecode, DecodeError
from .torrent import Torrent

logger = logging.getLogger('opalescence.' + __name__)


class TrackerError(Exception):
    """
    Raised when we encounter an error while communicating with the tracker.
    """
    pass


class Response:
    """
    Represents the response received from a tracker for a given torrent.
    """

    def __init__(self, resp: dict):
        self.response = resp

    @property
    def failure(self) -> str:
        """
        :return: None if no failure, failure reason from tracker otherwise
        """
        if b'failure reason' in self.response:
            return self.response[b'failure reason'].decode('utf-8')
        return None

    @property
    def interval(self) -> int:
        """
        :return: Interval the tracker asked us to use between requests
        """
        return self.response.get(b'interval', 0)

    @property
    def seeders(self) -> int:
        """
        :return: Number of peers in the swarm with the complete file
        """
        return self.response.get(b'complete', 0)

    @property
    def leechers(self) -> int:
        """
        :return: Number of peers in the swarm currently downloading the file
        """
        return self.response.get(b'incomplete', 0)

    @property
    def peers(self) -> list:
        """
        Decodes the peer list from a list of OrderedDict or a string of bytes into a list of ip, port tuples
        """
        peer_obj = self.response.get(b'peers')

        if isinstance(peer_obj, list):
            raise NotImplementedError()
        # this part is untested - dictionary response
        #    for peer in self.peers:
        #        assert (isinstance(peer, dict))
        #        if ["ip", "port", "peer id"] not in peer:
        #            raise TrackerError("Invalid peer list. Unable to decode {peer}".format(peer=peer))
        #        peers.append([peer.get("ip"), peer.get("port")])
        #        self.peer_list.add(Peer(peer.get("ip"), peer.get("port"), self.info_hash, self.peer_id))

        # bytestring response from tracker
        else:
            peer_len = len(peer_obj)
            if peer_len % 6 != 0:
                logger.debug("Invalid peer list. Length {length} should be a multiple of 6.".format(length=peer_len))
                raise TrackerError
            peers = [peer_obj[i:i + 6] for i in range(0, peer_len, 6)]
            return [(socket.inet_ntoa(p[:4]), struct.unpack(">H", p[4:])[0]) for p in peers]


class Tracker:
    """
    Represents the info from the tracker for a given torrent, providing methods
    to schedule the information to refresh
    """

    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.peer_id = "-OP0020-" + ''.join([str(random.randint(0, 9)) for _ in range(12)])

    async def make_request(self, event):
        """
        Makes a request to the tracker notifying it of our current stats.
        :param event:   optional,defaults to Started - One of Started, Stopped, Completed
                        to let the tracker know our current status
        :return:        True if response was received and Info updated, else False
        """
        params = {}
        params.setdefault("info_hash", self.torrent.info_hash)
        params.setdefault("peer_id", self.peer_id)
        params.setdefault("port", 6881)
        params.setdefault("uploaded", 0)
        params.setdefault("downloaded", 0)
        params.setdefault("left", self.torrent.total_file_size - 0)
        params.setdefault("compact", 1)
        if event:
            params.setdefault("event", event)

        logger.debug("Making request to tracker: {url}".format(url=self.torrent.announce))
        async with aiohttp.ClientSession() as client:
            async with client.get(self.torrent.announce, params=params) as r:
                if r.status == 200:
                    logger.debug("Request successful to: {url}".format(url=self.torrent.announce))
                    try:
                        data = await r.read()
                        return Response(bdecode(data))
                    except (TrackerError, DecodeError) as te:
                        logger.debug("Unable to decode tracker response.")
                        raise TrackerError from te
                else:
                    logger.debug("Request unsuccessful.")
                    raise TrackerError
