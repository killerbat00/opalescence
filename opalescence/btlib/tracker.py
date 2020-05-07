# -*- coding: utf-8 -*-

"""
Support for communication with an external tracker.
"""
import asyncio
import logging
from random import randint
from typing import Optional

import aiohttp
from btproto import TrackerConnection, Response, TrackerConnectionError, EVENT_STOPPED, EVENT_COMPLETED

logger = logging.getLogger(__name__)


def _generate_peer_id():
    """
    Generates a 20 byte long unique identifier for our peer.
    :return: our unique peer ID
    """
    return ("-OP0001-" + ''.join(str(randint(0, 9)) for _ in range(12))).encode("UTF-8")


class TrackerError:
    """
    Raised when there's an error with the Tracker.
    """


class Tracker:
    """
    Communication with the tracker.
    Does not currently support the announce-list extension from
    BEP 0012: http://bittorrent.org/beps/bep_0012.html
    Does not support the scrape convention.
    """

    DEFAULT_INTERVAL: int = 60  # 1 minute

    def __init__(self, *, info_hash: bytes, announce_url: str, left: int = 0):
        self.peer_id: bytes = _generate_peer_id()
        self.info_hash: bytes = info_hash
        self.announce_url: str = announce_url
        self.connection = TrackerConnection(info_hash=info_hash, announce_url=announce_url, peer_id=self.peer_id)
        self.http_client: aiohttp.ClientSession = aiohttp.ClientSession(loop=asyncio.get_event_loop())
        self.uploaded = 0
        self.downloaded = 0
        self.left = left

    async def announce(self, *, event: Optional[str] = None) -> Response:
        """
        Makes an announce request to the tracker.

        :raises TrackerError: if the tracker's HTTP code is not 200,
                              the tracker sent a failure, or we
                              are unable to bdecode the tracker's response.
        :returns: Response object representing the tracker's response
        """
        self.connection.update_stats(self.uploaded, self.downloaded, self.left)
        url: str = self.connection.announce(event=event)
        logger.debug(f"Making {event} announce to: {url}")

        async with self.http_client.get(url) as r:
            if not r.status == 200:
                logger.error(f"{url}: Unable to connect to tracker.")
                raise TrackerError
            data: bytes = await r.read()

            try:
                decoded_data: Response = self.connection.receive(data)
                return decoded_data
            except TrackerConnectionError as tce:
                raise TrackerError from tce

    async def cancel(self) -> None:
        """
        Informs the tracker we are gracefully shutting down.
        :raises TrackerError:
        """
        await self.announce(event=EVENT_STOPPED)
        await self.http_client.close()

    async def completed(self) -> None:
        """
        Informs the tracker we have completed downloading this torrent
        :raises TrackerError:
        """
        await self.announce(event=EVENT_COMPLETED)
        await self.http_client.close()
