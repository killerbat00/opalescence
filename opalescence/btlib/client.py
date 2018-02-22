# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""
import asyncio
import logging
from asyncio import Queue
from typing import List

from .metainfo import MetaInfoFile
from .protocol.messages import Block
from .protocol.peer import Peer
from .protocol.piece_handler import Requester, Writer
from .tracker import Tracker

logger = logging.getLogger(__name__)

MAX_PEER_CONNECTIONS = 1


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class ClientTorrent:
    """
    A torrent currently being handled by the client. This wraps the tracker, requester, and peers into a single
    API.
    """

    def __init__(self, torrent: MetaInfoFile):
        self.tracker = Tracker(torrent)
        self.available_peers = Queue()
        self.writer = Writer(torrent)
        self.current_peers: List[Peer] = []
        self.requester = Requester(torrent)
        self.loop = asyncio.get_event_loop()
        self.abort = False

    def stop(self):
        """
        Stop the download or seed.
        """
        logger.debug(f"Cancelling download/seed of {self.tracker.torrent.name}.")
        self.abort = True
        for peer in self.current_peers:
            peer.stop()
        self.tracker.close()
        self.writer.fd.close()

    async def cancel(self):
        """
        Cancels this download.
        """
        logger.debug(f"Cancelling download of {self.tracker.torrent.name}.")
        await self.tracker.cancel()
        self.tracker.close()

    async def start(self):
        """
        Schedules the recurring announce call with the tracker.
        TODO: needs work
        """
        self.current_peers = [Peer(self.available_peers,
                                   self.tracker.torrent.info_hash,
                                   self.tracker.peer_id,
                                   self.requester,
                                   self._on_block_retrieved)
                              for _ in range(MAX_PEER_CONNECTIONS)]

        previous = None
        interval = self.tracker.DEFAULT_INTERVAL

        while True:
            if self.requester.complete:
                logger.info(f"Torrent fully downloaded {self.tracker.torrent.name}")
                break
            if self.abort:
                logger.info(f"Aborting download of {self.tracker.torrent.name}.")
                break

            current = self.loop.time()
            if (not previous) or (previous + interval < current):
                response = await self.tracker.announce()

                if response:
                    previous = current
                    if response.interval:
                        interval = response.interval
                    self._empty_queue()
                    for peer in response.peers:
                        self.available_peers.put_nowait(peer)
            else:
                await asyncio.sleep(2)
        self.stop()

    def _empty_queue(self):
        while not self.available_peers.empty():
            self.available_peers.get_nowait()

    def _on_block_retrieved(self, block: Block) -> None:
        piece = self.requester.received_block(block)
        if piece:
            self.writer.write(piece)
