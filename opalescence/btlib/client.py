# -*- coding: utf-8 -*-

"""
Contains the client logic for opalescence.
The client is responsible for orchestrating communication with the tracker and between peers.
"""
import asyncio
import logging
from asyncio import Queue
from random import randint
from typing import Set, Optional

from opalescence.btlib.metainfo import MetaInfoFile
from .protocol.peer import PeerConnection, PeerInfo, PeerError
from .protocol.piece_handler import PieceRequester, FileWriter
from .tracker_connection import TrackerConnection, TrackerConnectionError

logger = logging.getLogger(__name__)

MAX_PEER_CONNECTIONS = 5


def _generate_peer_id():
    """
    Generates a 20 byte long unique identifier for our peer.
    :return: our unique peer ID
    """
    return ("-OP0001-" + ''.join(str(randint(0, 9)) for _ in range(12))).encode("UTF-8")


class ClientError(Exception):
    """
    Raised when the client encounters an error
    """


class ClientTorrent:
    """
    A torrent currently being handled by the client. This wraps the tracker, requester, and peers into a single
    API.
    """

    def __init__(self, torrent: MetaInfoFile, destination: str):
        def complete():
            logger.info("Torrent is complete! We should clean up...")
            for task in self.peer_tasks:
                task.cancel()

        self.torrent = torrent
        self.tracker = TrackerConnection(_generate_peer_id(), torrent)
        self.peer_q = Queue()
        self.writer = FileWriter(torrent, destination)
        self.requester = PieceRequester(torrent, self.writer, complete)
        self.current_peers: list = []
        self.connected_peers: Set[PeerConnection] = set()
        self.abort = False
        self._task: Optional[asyncio.Task] = None
        self.client_info = PeerInfo("localhost", 6973, _generate_peer_id())
        self.peer_tasks: list = []

    async def download(self):
        """
        Creates peer connections, attempts to connect to peers, calls the tracker, and
        serves as the main entrypoint for a torrent.
        TODO: needs work
        """
        previous = None
        interval = self.tracker.DEFAULT_INTERVAL

        while True:
            if self.requester.complete:
                await self.tracker.completed()
                for p in self.connected_peers:
                    p.read_task.cancel()
                    p.write_task.cancel()
                logger.info(f"Torrent fully downloaded {self}")
                break
            if self.abort:
                logger.info(f"Aborting download of {self.torrent.name}.")
                break

            current = asyncio.get_running_loop().time()
            if (not previous) or (previous + interval < current) or \
                len(self.connected_peers) == 0:
                try:
                    response = await self.tracker.announce()
                except TrackerConnectionError:
                    self.abort = True
                    continue

                if response:
                    previous = current
                    if response.interval:
                        interval = response.interval
                    self.current_peers = response.get_peers()
                    if not self.current_peers:
                        msg = f"{self}: No peers received."
                        logger.error(msg)
                        raise TrackerConnectionError(msg)
                    for x in range(MAX_PEER_CONNECTIONS):
                        if len(self.current_peers) == 0:
                            logger.info(f"{self}: No more peers to try connecting.")
                            break
                        ip, port = self.current_peers.pop()
                        logger.debug(f"IP: {ip}")
                        if ip == "10.10.2.55" and port == 6881:
                            continue
                        p = PeerConnection(PeerInfo(ip, port), self.torrent.info_hash,
                                           self.requester, self.client_info)
                        self.connected_peers.add(p)

                    for peer in self.connected_peers:
                        self.peer_tasks.append(asyncio.create_task(peer.download()))

                    if len(self.peer_tasks) > 0:
                        try:
                            await asyncio.gather(*self.peer_tasks)
                        except PeerError as pe:
                            self.connected_peers.remove(pe.peer)
                            if len(self.connected_peers) == 0:
                                await self.tracker.cancel()
                                self.abort = True
                                continue
            await asyncio.sleep(2)
