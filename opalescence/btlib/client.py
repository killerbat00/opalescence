# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""
import asyncio
import logging
from asyncio import Queue
from typing import Set

from opalescence.btlib.metainfo import MetaInfoFile
from .protocol.messages import Block
from .protocol.peer import Peer
from .protocol.piece_handler import Requester, FileWriter
from .tracker import Tracker, TrackerError

logger = logging.getLogger(__name__)

MAX_PEER_CONNECTIONS = 5


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
        self.tracker = Tracker(info_hash=torrent.info_hash, announce_url=torrent.announce_urls[0])
        self.available_peers = Queue()
        self.writer = FileWriter(torrent)
        self.current_peers: Set[Peer] = set()
        self.connected_peers: Set[Peer] = set()
        self.requester = Requester(torrent)
        self.loop = asyncio.get_event_loop()
        self.abort = False

    async def stop(self):
        """
        Immediately stops the download or seed.
        """
        logger.debug(f"Stopping peers and closing file.")
        for peer in self.current_peers:
            peer.cancel(False)
        self.writer.fd.close()

    async def cancel(self):
        """
        Cancels this download.
        """
        logger.debug(f"Cancelling tracker")
        await self.tracker.cancel()
        await self.stop()

    async def start(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        TODO: needs work
        """
        self.current_peers = [Peer(self.available_peers,
                                   self.tracker.info_hash,
                                   self.tracker.peer_id,
                                   self.requester,
                                   on_conn_close_cb=self._on_conn_close,
                                   on_conn_made_cb=self._on_conn_made,
                                   on_block_cb=self._on_block_retrieved)
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
            if (not previous) or (previous + interval < current) or \
                    len(self.connected_peers) == 0:
                try:
                    response = await self.tracker.announce()
                except TrackerError:
                    self.abort = True
                    continue

                if response:
                    previous = current
                    if response.interval:
                        interval = response.interval

                    while not self.available_peers.empty():
                        self.available_peers.get_nowait()

                    for peer in response.peers:
                        self.available_peers.put_nowait(peer)

            await asyncio.sleep(2)
        await self.stop()

    def _on_conn_close(self, peer: Peer) -> None:
        self.connected_peers.remove(peer)
        peer.restart()

    def _on_conn_made(self, peer: Peer) -> None:
        self.connected_peers.add(peer)

    def _on_block_retrieved(self, block: Block) -> None:
        piece = self.requester.received_block(block)
        if piece:
            self.writer.write(piece)
