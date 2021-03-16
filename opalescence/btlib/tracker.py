# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
"""

__all__ = ['Response', 'TrackerConnectionError', 'TrackerManager']

import asyncio
import dataclasses
import functools
import http.client
import logging
import socket
import struct
import urllib
from typing import Optional, List, Tuple
from urllib.parse import urlencode

from .bencode import Decoder
from .metainfo import MetaInfoFile
from .protocol.peer import PeerInfo

logger = logging.getLogger(__name__)

EVENT_STARTED = "started"
EVENT_COMPLETED = "completed"
EVENT_STOPPED = "stopped"


class Response:
    """
    Response received from the tracker after an announce request
    """

    def __init__(self, data: dict):
        self.data: dict = data
        self.failed: bool = "failure reason" in self.data

    @property
    def failure_reason(self) -> Optional[str]:
        """
        :return: the failure reason
        """
        if self.failed:
            return self.data["failure reason"].decode("UTF-8")

    @property
    def interval(self) -> int:
        """
        :return: the tracker's specified interval between announce requests
        """
        min_interval = self.data.get("min interval", None)
        if not min_interval:
            return self.data.get("interval", TrackerManager.DEFAULT_INTERVAL)
        interval = self.data.get("interval", TrackerManager.DEFAULT_INTERVAL)
        return min(min_interval, interval)

    @property
    def tracker_id(self) -> Optional[str]:
        """
        :return: the tracker id
        """
        tracker_id = self.data.get("tracker id")
        if tracker_id:
            return tracker_id.decode("UTF-8")

    @property
    def complete(self) -> int:
        """
        :return: seeders, the number of peers with the entire file
        """
        return self.data.get("complete", 0)

    @property
    def incomplete(self) -> int:
        """
        :return: leechers, the number of peers that are not seeders
        """
        return self.data.get("incomplete", 0)

    def get_peers(self) -> Optional[List[Tuple[str, int]]]:
        """
        :raises TrackerConnectionError:
        :return: the list of peers. The response can be given as a
        list of dictionaries about the peers, or a string
        encoding the ip address and ports for the peers
        """
        peers = self.data.get("peers")

        if not peers:
            return

        if isinstance(peers, bytes):
            split_peers = [peers[i:i + 6] for i in range(0, len(peers), 6)]
            p = [(socket.inet_ntoa(p[:4]), struct.unpack(">H", p[4:])[0]) for
                 p in split_peers]
            return p
        elif isinstance(peers, list):
            return [(p["ip"].decode("UTF-8"), int(p["port"])) for p in peers]
        else:
            raise TrackerConnectionError(f"Unable to decode `peers` key from response")


class TrackerConnectionError(Exception):
    """
    Raised when there's an error with the Tracker.
    """

    def __init__(self, failure_reason: Optional[str] = ""):
        self.failure_reason = failure_reason


def receive(data: bytes) -> Response:
    tracker_resp = Response(Decoder(data).decode())
    if tracker_resp.failed:
        raise TrackerConnectionError(tracker_resp.failure_reason)
    return tracker_resp


@dataclasses.dataclass
class TrackerParameters:
    info_hash: bytes
    peer_id: bytes
    port: int
    uploaded: int
    downloaded: int
    left: int
    compact: int
    event: str


def delegate_to_executor(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        return await asyncio.get_running_loop().run_in_executor(None,
                                                                functools.partial(func, *args, **kwargs))

    return wrapper


@delegate_to_executor
def request(url: str, params: TrackerParameters) -> Response:
    url = urllib.parse.urlparse(url)
    scheme = url.scheme
    conn = None
    if scheme == 'http':
        conn = http.client.HTTPConnection(url.netloc, timeout=5)
    elif scheme == 'https':
        conn = http.client.HTTPSConnection(url.netloc, timeout=5)

    try:
        if conn is None or not params:
            raise TrackerConnectionError('Cannot request on uninitialized tracker.')

        q = urllib.parse.parse_qs(url.query)
        q.update(dataclasses.asdict(params))
        path = url._replace(scheme="", netloc="", query=urllib.parse.urlencode(q)).geturl()
        conn.request("GET", path)
        return receive(conn.getresponse().read())
    finally:
        conn.close()


class TrackerManager:
    """
    Communication with the tracker.
    Does not currently support the announce-list extension from
    BEP 0012: http://bittorrent.org/beps/bep_0012.html. Instead, when one tracker
    disconnects or fails, or runs out of trackers, we hop round robin to the next tracker.
    Does not support the scrape convention.
    """
    DEFAULT_INTERVAL: int = 60  # 1 minute

    def __init__(self, local_info: PeerInfo, meta_info: MetaInfoFile, stats: dict):
        self.peer_id: bytes = local_info.peer_id_bytes
        self.info_hash: bytes = meta_info.info_hash
        self.announce_urls: List[List[str]] = meta_info.announce_urls
        self.stats = stats
        self.port = local_info.port
        self.interval = self.DEFAULT_INTERVAL

    async def announce(self, event: str = "") -> Response:
        """
        Makes an announce request to the tracker.

        :raises TrackerConnectionError: if the tracker's HTTP code is not 200,
                                        we timed out making a request to the tracker,
                                        the tracker sent a failure, or we
                                        are unable to bdecode the tracker's response.
        :returns: Response object representing the tracker's response
        """
        if not event:
            event = EVENT_STARTED

        # TODO: respect proper order of announce urls according to BEP 0012
        url = self.announce_urls[0][0]
        if not url:
            raise TrackerConnectionError("Unable to make request - no url.")

        params = TrackerParameters(self.info_hash, self.peer_id, self.port, self.stats.get("uploaded", 0),
                                   self.stats.get("downloaded", 0), self.stats.get("left", 0), 1, event)

        try:
            logger.info(f"Making {event} announce to: {url}")
            decoded_data = await request(url, params)
            self.interval = decoded_data.interval
            return decoded_data

        except Exception as e:
            logger.exception(f"{self}: {type(e).__name__} received in TrackerManager.announce", exc_info=True)
            raise TrackerConnectionError

    async def cancel(self) -> None:
        """
        Informs the tracker we are gracefully shutting down.
        :raises TrackerError:
        """
        await self.announce(event=EVENT_STOPPED)

    async def completed(self) -> None:
        """
        Informs the tracker we have completed downloading this torrent
        :raises TrackerError:
        """
        await self.announce(event=EVENT_COMPLETED)
