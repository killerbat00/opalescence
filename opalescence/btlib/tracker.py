# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
"""

import asyncio
import logging
import random
import socket
import struct
from typing import Union
from urllib.parse import urlencode

import aiohttp

from opalescence.btlib import bencode
from . import log_and_raise
from .metainfo import MetaInfoFile

logger = logging.getLogger(__name__)


class TrackerError(Exception):
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
    # TODO: implement scrape convention support.
    DEFAULT_INTERVAL = 60  # 1 minute

    def __init__(self, torrent: MetaInfoFile):
        self.torrent = torrent
        self.http_client = aiohttp.ClientSession(loop=asyncio.get_event_loop())
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

        :raises TrackerError: if the tracker's HTTP code is not 200, the tracker sent a failure, or we
                              are unable to bdecode the tracker's response.
        :returns: Response object representing the tracker's response
        """
        url = self._make_url()
        decoded_data = None

        logger.debug(f"Making {self.event} announce to: {url}")
        async with self.http_client.get(url) as r:
            data = await r.read()
            if r.status != 200:
                log_and_raise(f"Unable to connect to the tracker.\n{data}", logger, TrackerError)

            try:
                decoded_data = bencode.Decoder(data).decode()
            except bencode.DecodeError as e:
                log_and_raise(f"Unable to decode tracker response.\n{data}", logger, TrackerError, e)

            tr = Response(decoded_data)
            if tr.failed:
                log_and_raise(f"Failed announce call to tracker {url}\n{tr.failure_reason}", logger, TrackerError)

            if self.event:
                self.event = ""
            return Response(decoded_data)

    async def cancel(self) -> None:
        """
        Informs the tracker we are gracefully shutting down.
        :raises TrackerError:
        """
        self.event = "stopped"
        await self.announce()
        return

    async def completed(self) -> None:
        """
        Informs the tracker we have completed downloading this torrent
        :raises TrackerError:
        """
        self.event = "completed"
        await self.announce()
        return

    def _make_url(self) -> str:
        """
        Builds and escapes the url used to communicate with the tracker.
        Currently only uses the announce key

        :raises TrackerError:
        :return: tracker's announce url with correctly escaped and encoded parameters
        """
        # TODO: implement proper announce-list handling
        return self.torrent.meta_info[b"announce"].decode("UTF-8") + "?" + urlencode(self._make_params())

    def _make_params(self) -> dict:
        """
        Builds the parameter dictionary the tracker expects for announce requests.

        :return: dictionary of properly encoded parameters
        """
        params = {"info_hash": self.torrent.info_hash,
                  "peer_id": self.peer_id,
                  "port": self.port,
                  "uploaded": self.uploaded,
                  "downloaded": self.downloaded,
                  "left": self.left,
                  "compact": 1}
        if self.event:
            params["event"] = self.event
        return params

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
        :return: the failure reason
        """
        if self.failed:
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
        tracker_id = self.data.get(b"tracker id")
        if tracker_id:
            return tracker_id.decode("UTF-8")
        return

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
        :raises TrackerError:
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
            log_and_raise(f"Unable to decode peers {peers}", logger, TrackerError)
