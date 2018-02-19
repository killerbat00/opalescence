# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
"""

import asyncio
import logging
import socket
import struct
from random import randint
from typing import Union, Optional
from urllib.parse import urlencode

import aiohttp

from opalescence.btlib import bencode
from .metainfo import MetaInfoFile

logger = logging.getLogger(__name__)


def _generate_peer_id():
    """
    Generates a 20 byte long unique identifier for our peer.
    :return: our unique peer ID
    """
    return ("-OP0001-" + ''.join(str(randint(0,9)) for _ in range(12))).encode("UTF-8")


class TrackerError(Exception):
    """
    Raised when we encounter an error while communicating with the tracker.
    """
    pass


class Tracker:
    """
    Communication with the tracker.
    Does not currently support the announce-list extension from
    BEP 0012: http://bittorrent.org/beps/bep_0012.html
    Does not support the scrape convention.
    """

    # TODO: implement announce-list extension support.
    # TODO: implement scrape convention support.
    DEFAULT_INTERVAL = 60  # 1 minute

    def __init__(self, torrent: MetaInfoFile):
        self.torrent = torrent
        self.http_client = aiohttp.ClientSession(loop=asyncio.get_event_loop())
        self.peer_id = _generate_peer_id()
        self.port = 6881
        self.uploaded = 0
        self.downloaded = 0
        self.left = 0
        self.event = "started"

    async def announce(self) -> "Response":
        """
        Makes an announce request to the tracker.

        :raises TrackerError: if the tracker's HTTP code is not 200,
                              the tracker sent a failure, or we
                              are unable to bdecode the tracker's response.
        :returns: Response object representing the tracker's response
        """
        url = self._make_url()
        logger.debug(f"Making {self.event} announce to: {url}")

        async with self.http_client.get(url) as r:
            if not r.status == 200:
                logger.error(f"{url}: Unable to connect to tracker.")
                raise TrackerError
            data = await r.read()

        try:
            decoded_data = bencode.Decoder(data).decode()
        except bencode.DecodeError as e:
            logger.error(f"{url}: Unable to decode tracker response.")
            logger.info(e, exc_info=True)
            raise TrackerError from e

        tracker_resp = Response(decoded_data)
        if tracker_resp.failed:
            logger.error(f"{url}: Failed announce call to tracker.")
            raise TrackerError

        if self.event:
            self.event = ""

        return tracker_resp

    async def cancel(self) -> None:
        """
        Informs the tracker we are gracefully shutting down.
        :raises TrackerError:
        """
        self.event = "stopped"
        await self.announce()

    async def completed(self, already_complete: bool=False) -> None:
        """
        Informs the tracker we have completed downloading this torrent
        :param already_complete: True if already completed (won't send complete event to tracker)
        :raises TrackerError:
        """
        if not already_complete:
            self.event = "completed"
        await self.announce()

    def _make_url(self) -> str:
        """
        Builds and escapes the url used to communicate with the tracker.
        Currently only uses the announce key

        :raises TrackerError:
        :return: tracker's announce url with urlencoded parameters
        """
        # TODO: implement proper announce-list handling
        return self.torrent.meta_info[b"announce"].decode("UTF-8") + \
               "?" + urlencode(self._make_params())

    def _make_params(self) -> dict:
        """
        Builds the parameters the tracker expects for announce requests.

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
        asyncio.get_event_loop().run_until_complete(self.http_client.close())


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
        :return: the minimum interval
        """
        return self.data.get(b"min interval", 0)

    @property
    def tracker_id(self) -> Optional[str]:  # or maybe bytes?
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
    def peers(self) -> Optional[list]:
        """
        :raises TrackerError:
        :return: the list of peers. The response can be given as a
        list of dictionaries about the peers, or a string
        encoding the ip address and ports for the peers
        """
        peers = self.data.get(b"peers")

        if not peers:
            return

        if isinstance(peers, bytes):
            logger.debug("Decoding binary model peers.")
            split_peers = [peers[i:i + 6] for i in range(0, len(peers), 6)]
            p = [(socket.inet_ntoa(p[:4]), struct.unpack(">H", p[4:])[0]) for
                 p in split_peers]
            return p
        elif isinstance(peers, list):
            logger.debug("Decoding dictionary model peers.")
            p = [(p[b"ip"].decode("UTF-8"), p[b"port"]) for p in peers]
            return p
        else:
            logger.error(f"Unable to decode peers {peers}")
            raise TrackerError
