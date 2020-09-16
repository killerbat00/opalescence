# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
"""
import asyncio
import logging
import socket
import struct
from typing import Optional, List
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout

from opalescence.btlib.bencode import Decoder
from opalescence.btlib.metainfo import MetaInfoFile

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
            return self.data.get("interval", TrackerConnection.DEFAULT_INTERVAL)
        interval = self.data.get("interval", TrackerConnection.DEFAULT_INTERVAL)
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

    def get_peers(self) -> Optional[list]:
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
            p = [(p["ip"].decode("UTF-8"), p["port"]) for p in peers]
            return p
        else:
            raise TrackerConnectionError(f"Unable to decode `peers` key from response")


class TrackerConnectionError(Exception):
    """
    Raised when there's an error with the Tracker.
    """

    def __init__(self, failure_reason: Optional[str]):
        self.failure_reason = failure_reason


def receive(data: bytes) -> Response:
    tracker_resp = Response(Decoder(data).decode())
    if tracker_resp.failed:
        raise TrackerConnectionError(tracker_resp.failure_reason)
    return tracker_resp


class TrackerConnection:
    """
    Communication with the tracker.
    Does not currently support the announce-list extension from
    BEP 0012: http://bittorrent.org/beps/bep_0012.html
    Does not support the scrape convention.
    """

    DEFAULT_INTERVAL: int = 60  # 1 minute

    def __init__(self, peer_id: bytes, meta_info: MetaInfoFile):
        self.peer_id: bytes = peer_id
        self.info_hash: bytes = meta_info.info_hash
        self.announce_urls: List[List[str]] = meta_info.announce_urls
        self.http_client: ClientSession = ClientSession(timeout=ClientTimeout(5))
        self.uploaded = 0
        self.downloaded = 0
        self.left: int = meta_info.total_size
        self.port = 6881
        self.last_requests = {}
        self.interval = self.DEFAULT_INTERVAL

    def _get_url_params(self, event: str = "") -> str:
        """
        :param event: the event sent in the request when starting, stopping, and completing
        :return: Returns a dictionary of the request parameters expected by the tracker.
        """
        params = {"info_hash": self.info_hash,
                  "peer_id": self.peer_id,
                  "port": self.port,  # TODO: We tell the tracker this, but don't actually listen on this port.
                  "uploaded": self.uploaded,
                  "downloaded": self.downloaded,
                  "left": self.left,
                  "compact": 1,
                  "event": event}
        # return urlencode(params)
        return params

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

        params = self._get_url_params(event)
        if not params:
            raise TrackerConnectionError(f"{url}: Unable to make URL params.")

        try:
            logger.debug(f"Making {event} announce to: {url}")
            async with self.http_client.get(f"{url}?{urlencode(params)}") as r:
                if r.status != 200:
                    logger.error(f"{url}: Unable to connect to tracker.")
                    raise TrackerConnectionError("Non-200 HTTP status.")

                data: bytes = await r.read()
                decoded_data: Response = receive(data)
                self.interval = decoded_data.interval
                return decoded_data

        except asyncio.TimeoutError:
            logger.error(f"{url}: Timeout connecting...")
            raise TrackerConnectionError(f"{url}: Timeout connecting...")

        except TrackerConnectionError as tce:
            logger.error(f"{url}: Unable to connect to tracker. "
                         f"{tce.failure_reason}")
            raise tce

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
