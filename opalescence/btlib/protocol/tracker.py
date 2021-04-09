# -*- coding: utf-8 -*-

"""
Support for communication with HTTP trackers.
"""

from __future__ import annotations

__all__ = ['TrackerResponse', 'TrackerConnectionError', 'TrackerConnection']

import asyncio
import contextlib
import dataclasses
import functools
import http.client
import logging
import socket
import struct
import urllib
from collections import deque
from typing import Optional, List, Tuple
from urllib.parse import urlencode

from .bencode import *
from .metainfo import MetaInfoFile
from .peer_info import PeerInfo
from ..events import Event

logger = logging.getLogger(__name__)

EVENT_STARTED = "started"
EVENT_COMPLETED = "completed"
EVENT_STOPPED = "stopped"


class TrackerConnectionError(Exception):
    """
    Raised when there's an error with the TrackerConnection.
    """


class NoTrackersError(Exception):
    """
    Raised when there are no trackers to accept an announce.
    """


class TrackerConnectionCancelledError(Exception):
    """
    Raised when the connection has been cancelled by the application.
    """


class PeersReceived(Event):
    """
    Raised when peers are received from the tracker.
    """

    def __init__(self, peer_list: list[PeerInfo]):
        name = self.__class__.__name__
        super().__init__(name, peer_list)


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


async def http_request(url, params: TrackerParameters) -> TrackerResponse:
    url = urllib.parse.urlparse(url)
    query_params = urllib.parse.parse_qs(url.query)
    query_params.update(dataclasses.asdict(params))
    conn = None

    try:
        if not (params or url):
            raise TrackerConnectionError

        if url.scheme == "http":
            conn = http.client.HTTPConnection(url.netloc, timeout=5)
        elif url.scheme == "https":
            conn = http.client.HTTPSConnection(url.netloc, timeout=5)

        path = url._replace(scheme="", netloc="", query=urllib.parse.urlencode(query_params)).geturl()
        await asyncio.get_running_loop().run_in_executor(
            None, functools.partial(conn.request, "GET", path)
        )
        resp = conn.getresponse()
        if resp.status != 200:
            raise TrackerConnectionError
        tracker_resp = TrackerResponse(Decode(resp.read()))
        if tracker_resp.failed:
            raise TrackerConnectionError
        return tracker_resp
    finally:
        if conn is not None:
            conn.close()


class TrackerConnection:
    """
    Communication with the tracker.
    Does not currently support the announce-list extension from
    BEP 0012: http://bittorrent.org/beps/bep_0012.html. Instead, when one tracker
    disconnects or fails, or runs out of trackers, we hop round robin to the next tracker.
    Does not support the scrape convention.

    TODO: Allow multiple trackers to run concurrently?
    """
    DEFAULT_INTERVAL: int = 60  # 1 minute

    def __init__(self, local_info, meta_info: MetaInfoFile):
        self.client_info = local_info
        self.torrent = meta_info
        self.announce_urls = deque(set(url for tier in meta_info.announce_urls for url in tier))
        self.interval = self.DEFAULT_INTERVAL
        self.task: Optional[asyncio.Task] = None

    def start(self):
        if self.task is None:
            self.task = asyncio.create_task(self._recurring_announce())

    async def _recurring_announce(self):
        """
        Responsible for making the recurring request for peers.
        """
        if len(self.announce_urls) == 0:
            raise NoTrackersError

        event = EVENT_STARTED

        while not self.task.cancelled():
            try:
                await self.announce(event)

                if len(self.announce_urls) == 0:
                    break

                event = ""
                await asyncio.sleep(self.interval)
            except (TrackerConnectionCancelledError, asyncio.CancelledError):
                break
            except TrackerConnectionError:
                continue
            except NoTrackersError:
                self.task.cancel()
        logger.info(f"Recurring announce task ended.")

    async def announce(self, event: str = "") -> None:
        """
        Makes an announce request to the tracker.

        :raises TrackerConnectionError: if the tracker's HTTP code is not 200,
                                        we timed out making a request to the tracker,
                                        the tracker sent a failure, or we
                                        are unable to bdecode the tracker's response.
        :raises NoTrackersError:        if there are no tracker URls to query.
        :raises TrackerConnectionCancelledError: if the task has been cancelled.
        :returns: TrackerResponse object representing the tracker's response
        """
        # TODO: respect proper order of announce urls according to BEP 0012.
        if len(self.announce_urls) == 0:
            raise NoTrackersError

        if self.task.cancelled():
            raise TrackerConnectionCancelledError

        remaining = self.torrent.remaining
        if remaining == 0 and not event:
            event = EVENT_COMPLETED

        url = self.announce_urls.popleft()
        params = TrackerParameters(self.torrent.info_hash, self.client_info.peer_id_bytes, self.client_info.port,
                                   0, self.torrent.present, remaining, 1, event)

        logger.info(f"Making {event} announce to: {url}")
        try:
            decoded_data = await http_request(url, params)
            if decoded_data is None:
                raise TrackerConnectionError
        except Exception as e:
            logger.error(f"{type(e).__name__} received in announce.")
            raise TrackerConnectionError from e

        if event != EVENT_COMPLETED and event != EVENT_STOPPED:
            self.interval = decoded_data.interval
            self.announce_urls.appendleft(url)

            peers = []
            for peer in decoded_data.get_peers():
                peer_info = PeerInfo(peer[0], peer[1])
                if peer_info == self.client_info:
                    logger.info(f"Ignoring peer. It's us...")
                    continue
                peers.append(peer_info)
            PeersReceived(peers)

    async def cancel_announce(self) -> None:
        """
        Informs the tracker we are gracefully shutting down.
        :raises TrackerConnectionError:
        """
        with contextlib.suppress(TrackerConnectionError, NoTrackersError, TrackerConnectionCancelledError):
            await self.announce(event=EVENT_STOPPED)
            if not self.task.cancelled():
                self.task.cancel()

    async def completed(self) -> None:
        """
        Informs the tracker we have completed downloading this torrent
        :raises TrackerConnectionError:
        """
        with contextlib.suppress(TrackerConnectionError, NoTrackersError, TrackerConnectionCancelledError):
            await self.announce(event=EVENT_COMPLETED)
            if not self.task.cancelled():
                self.task.cancel()


class TrackerResponse:
    """
    TrackerResponse received from the tracker after an announce request.
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
            return self.data.get("failure reason", b"Unknown").decode("UTF-8")

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
    def seeders(self) -> int:
        """
        :return: seeders, the number of peers with the entire file
        """
        return self.data.get("complete", 0)

    @property
    def leechers(self) -> int:
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
            raise TrackerConnectionError
