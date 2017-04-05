# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""
import logging

from . import log_and_raise
from .torrent import Torrent
from .tracker import Tracker, TrackerError

logger = logging.getLogger(__name__)


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class Client:
    """
    Handles communication with the tracker and between peers
    """

    def __init__(self, torrent: Torrent):
        self.torrent = torrent
        self.tracker = Tracker(self.torrent)
        self.peers = []

        self.start_announcing()

    async def start_announcing(self):
        """
        Schedules the recurring announce call with the tracker.
        """
        try:
            resp = await self.tracker.announce()
        except TrackerError as te:
            log_and_raise(f"Unable to make announce call to {self.tracker}", logger, ClientError, te)
