# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
"""

import logging
import random
import socket
import struct
from typing import Union
from urllib.parse import urlencode

import aiohttp

from opalescence.btlib import bencode
from .torrent import Torrent

logger = logging.getLogger('opalescence.' + __name__)


class TrackerCommError(Exception):
    """
    Raised when we encounter an error while communicating with the tracker.
    """
    pass


class Tracker:
    """
    Communication with the tracker.
    Does not currently support the announce-list extension from BEP 0012: http://bittorrent.org/beps/bep_0012.html
    Does not support the scrape convention.
    """

    # TODO: implement announce-list extension support.
    # TODO: implement scrape convention support

    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.http_client = aiohttp.ClientSession()
        self.peer_id = ("-OP0001-" + ''.join([str(random.randint(0, 9)) for _ in range(12)])).encode("UTF-8")
        self.tracker_id = None
        self.port = 6881
        self.uploaded = 0
        self.downloaded = 0
        self.left = 0
        self.event = "started"

    async def announce(self) -> "Response":
        """
        Makes an announce request to the tracker.

        :raises TrackerCommError: if the tracker's HTTP code is not 200, the tracker sent a failure, or we
                                  are unable to bdecode the tracker's response.
        :returns: Response object representing the tracker's response
        """
        url = self._make_url()

        logger.debug(f"Making announce request: {url}")
        async with self.http_client.get(url) as r:
            data = await r.read()
            if r.status != 200:
                error_msg = f"Unable to connect to the tracker.\n{data}"
                logger.error(error_msg)
                raise TrackerCommError(error_msg)

            try:
                decoded_data = bencode.Decoder(data).decode()
            except bencode.DecodeError as e:
                error_msg = f"Unable to decode tracker response {data}"
                logger.error(error_msg)
                raise TrackerCommError(error_msg) from e
            tr = Response(decoded_data)
            if tr.failed:
                error_msg = f"Announce call to tracker {url} failed.\n{tr.failure_reason}"
                logger.error(error_msg)
                raise TrackerCommError(error_msg)
            return Response(decoded_data)

    def _make_url(self) -> str:
        """
        Builds and escapes the url used to communicate with the tracker.
        Currently only uses the announce key

        ;return: tracker's announce url with correctly escaped and encoded parameters
        """
        # TODO: implement proper announce-list handling
        return self.torrent.meta_info[b"announce"].decode("UTF-8") + "?" + urlencode(self._make_params())

    def _make_params(self) -> dict:
        """
        Builds the parameter dictionary the tracker expects for announce requests.

        :return: dictionary of properly encoded parameters
        """
        # TODO: implement proper tracker event sending
        return {"info_hash": self.torrent.info_hash,
                "peer_id": self.peer_id,
                "port": self.port,
                "uploaded": self.uploaded,
                "downloaded": self.downloaded,
                "left": self.left,
                "compact": 1,
                "event": self.event}

    def close(self):
        """
        Closes the http_client session
        """
        self.http_client.close()


class Response:
    """
    Response received from the tracker after an announce request
    """

    def __init__(self, data: dict):
        self.data = data
        self.failed = b"failure reason" in self.data

    @property
    def failure_reason(self) -> Union[str, None]:
        """
        If the request failed, this will be the only key
        :return: the failure reason
        """
        if self.failed:
            # not sure if this should be decoded or not
            return self.data[b"failure reason"].decode("UTF-8")
        return None

    @property
    def interval(self) -> int:
        """
        :return: the tracker's specified interval between announce requests
        """
        return self.data.get(b"interval", 0)

    @property
    def min_interval(self) -> int:
        """
        :return: the minimum interval, if specified we can't make requests more frequently than this
        """
        return self.data.get(b"min interval", 0)

    @property
    def tracker_id(self) -> Union[str, None]:  # or maybe bytes?
        """
        :return: the tracker id
        """
        return self.data.get(b"tracker id")

    @property
    def complete(self) -> int:
        """
        :return: seeders, the number of peers with the entire file
        """
        return self.data.get(b"complete", 0)

    @property
    def incomplete(self) -> int:
        """
        :return: leechers, the number of peers that are not seeders
        """
        return self.data.get(b"incomplete", 0)

    @property
    def peers(self) -> Union[list, None]:
        """
        :return: the list of peers. The response can be given as a list of dictionaries about the peers, or a string
        encoding the ip address and ports for the peers
        """
        peers = self.data.get(b"peers")

        if not peers:
            return

        if isinstance(peers, bytes):
            logger.debug("Decoding binary model peers.")
            split_peers = [peers[i:i + 6] for i in range(0, len(peers), 6)]
            return [(socket.inet_ntoa(p[:4]), struct.unpack(">H", p[4:])[0]) for p in split_peers]
        elif isinstance(peers, list):
            logger.debug("Decoding dictionary model peers.")
            return [(p[b"ip"].decode("UTF-8"), p[b"port"]) for p in peers]
        else:
            error_msg = f"Unable to decode peers: {peers}."
            logger.error(error_msg)
            raise TrackerCommError(error_msg)
