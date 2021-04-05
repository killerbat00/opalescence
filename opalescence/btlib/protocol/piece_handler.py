# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""

__all__ = ['PieceRequester', 'FileWriter']

import asyncio
import dataclasses
import functools
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Optional

import bitstring

from .messages import Request, Piece, Block
from ..metainfo import MetaInfoFile, FileItem
from ..utils import ensure_dir_exists

logger = logging.getLogger(__name__)


def delegate_to_executor(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        await self._lock.acquire()
        try:
            return await asyncio.get_running_loop().run_in_executor(None,
                                                                    functools.partial(func, self, *args, **kwargs))
        finally:
            self._lock.release()

    return wrapper


@dataclasses.dataclass
class WriteBuffer:
    buffer = b''
    offset = 0


class FileWriter:
    WRITE_BUFFER_SIZE = 2 ** 13  # 8kb

    def __init__(self, torrent: MetaInfoFile):
        self._files: Dict[int, FileItem] = dict(torrent.files)
        self._total_size = sum([file.size for file in self._files.values()])
        self._torrent = torrent
        self._base_dir = torrent.destination
        self._lock = asyncio.Lock()

    def _write_data(self, data_to_write, file, offset):
        """
        Writes data to the file in an executor so we don't block the main event loop.
        :param data_to_write: data to write to file
        :param file: FileItem containing file path and size
        :param offset: Offset into the file to begin writing this data
        """
        p = Path(self._base_dir) / file.path
        logger.info(f"Writing data to: {p}")
        try:
            ensure_dir_exists(p)
            with open(p, "ab+") as fd:
                fd.seek(offset, 0)
                fd.write(data_to_write)
                fd.flush()
        except (OSError, Exception):
            logger.exception(f"Encountered exception when writing to {p}", exc_info=True)
            raise

    @delegate_to_executor
    def write(self, piece: Piece):
        """
        Buffers (and eventually) writes the piece's
        data to the appropriate file(s).
        :param piece: piece to write
        """
        # TODO: Handle trying to write incomplete pieces
        assert piece.complete

        offset = piece.index * self._torrent.piece_length
        data_to_write = piece.data
        while data_to_write:
            file_num, file_offset = FileItem.file_for_offset(self._torrent.files, offset)
            file = self._torrent.files[file_num]
            if file_num >= len(self._torrent.files):
                logger.error("Too much data and not enough files...")
                raise

            if file_offset + len(data_to_write) > file.size:
                data_for_file = data_to_write[:file.size - file_offset]
                data_to_write = data_to_write[file.size - file_offset:]
                offset += len(data_for_file)
            else:
                data_for_file = data_to_write
                data_to_write = None
            self._write_data(data_for_file, file, file_offset)


class PieceRequester:
    """
    Responsible for requesting and downloading pieces from peers.
    A single requester is shared between all peers to which the local peer is connected.

    We currently use a naive sequential strategy.
    """

    def __init__(self, torrent: MetaInfoFile, stats):
        self.torrent = torrent
        self.piece_peer_map: Dict[int, Set[str]] = {i: set() for i in range(self.torrent.num_pieces)}
        self.peer_piece_map: Dict[str, Set[int]] = defaultdict(set)
        self.pending_requests: List[Request] = []
        self.writer = FileWriter(torrent)
        self.stats = stats

    @property
    def complete(self):
        return self.torrent.remaining == 0

    def add_available_piece(self, peer_id: str, index: int):
        """
        Called when a peer advertises it has a piece available.

        :param peer_id: The peer that has the piece
        :param index: The index of the piece
        """
        self.piece_peer_map[index].add(peer_id)
        self.peer_piece_map[peer_id].add(index)

    def add_peer_bitfield(self, peer_id: str, bitfield: bitstring.BitArray):
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer_id:  The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        for i, b in enumerate(bitfield):
            if b:
                self.add_available_piece(peer_id, i)

    def remove_pending_requests_for_peer(self, peer_id: str):
        """
        Removes all pending requests for a peer.
        Called when the peer disconnects or chokes us.

        :param peer_id: peer whose pending requests ew should remove
        """
        for request in self.pending_requests:
            if request.peer_id == peer_id:
                self.pending_requests.remove(request)

    def remove_request(self, request: Request) -> bool:
        """
        Removes all pending requests that match the given request.

        :param request: `Request` to remove from pending requests.
        :return: True if removed, False otherwise
        """
        removed = False
        while request in self.pending_requests:
            self.pending_requests.remove(request)
            removed = True
        return removed

    def remove_requests_for_piece(self, piece_index: int):
        """
        Removes all pending requests with the given piece index.

        :param piece_index: piece index whose requests should be removed
        """
        for i, request in enumerate(self.pending_requests):
            if request.index == piece_index:
                del self.pending_requests[i]

    def remove_peer(self, peer_id: str):
        """
        Removes a peer from this requester's data structures in the case
        that our communication with that peer has stopped

        :param peer_id: peer to remove
        """
        for _, peer_set in self.piece_peer_map.items():
            if peer_id in peer_set:
                peer_set.discard(peer_id)

        if peer_id in self.peer_piece_map:
            del self.peer_piece_map[peer_id]

        self.remove_pending_requests_for_peer(peer_id)

    async def received_block(self, peer_id: str, block: Block):
        """
        Called when we've received a block from the remote peer.
        First, see if there are other blocks from that piece already downloaded.
        If so, add this block to the piece and pend a request for the remaining blocks
        that we would need.

        :param peer_id: The peer who sent the block
        :param block: The piece message with the data and e'erthang
        """
        logger.info(f"{peer_id} sent {block}")
        self.peer_piece_map[peer_id].add(block.index)
        self.piece_peer_map[block.index].add(peer_id)

        if block.index > len(self.torrent.pieces):
            logger.debug(f"Disregarding. Piece {block.index} does not exist.")

        piece = self.torrent.pieces[block.index]
        if piece.complete:
            logger.debug(f"Disregarding. I already have {block}")
            return

        # Remove the pending requests for this block if there are any
        r = Request(block.index, block.begin, min(piece.remaining, Request.size))
        if not self.remove_request(r):
            logger.debug(f"Disregarding. I did not request {block}")
            return

        self.stats.downloaded += len(block.data)
        self.stats.left -= len(block.data)

        piece.add_block(block)
        if piece.complete:
            await self.piece_complete(piece)

    async def piece_complete(self, piece: Piece):
        h = piece.hash()
        if h != self.torrent.piece_hashes[piece.index]:
            logger.error(
                f"Hash for received piece {piece.index} doesn't match\n"
                f"Received: {h}\n"
                f"Expected: {self.torrent.piece_hashes[piece.index]}")
            piece.reset()
        else:
            logger.info(f"Completed piece received: {piece}")
            self.remove_requests_for_piece(piece.index)
            await self.writer.write(piece)
            piece.mark_complete()

    def next_request_for_peer(self, peer_id: str) -> Optional[Request]:
        """
        Finds the next request that we can send to the peer.

        Works like this:
        1. Check each piece the peer has to find the first incomplete piece.
        2. Request the next block for the first incomplete piece found.
        3. If we already have a request for an incomplete piece's next block, return.
        4. If none available, the peer is useless to us.

        TODO: Multiple per-block pending requests.

        :param peer_id: peer requesting a piece
        :return: piece's index or None if not available
        """
        if self.complete:
            logger.info("Already complete.")
            return

        if len(self.pending_requests) >= 50:
            logger.error(f"Too many currently pending requests.")
            return

        # Find the next piece index in the pieces we are downloading that the
        # peer said it could send us
        for i in self.peer_piece_map[peer_id]:
            piece = self.torrent.pieces[i]
            if piece.complete:
                continue

            size = min(piece.remaining, Request.size)
            request = Request(i, piece.next_block, size, peer_id)
            while request in self.pending_requests:
                logger.info(f"{peer_id}: We have an outstanding request for {request}")
                return

            logger.info(f"{peer_id}: Successfully got request {request}.")
            self.pending_requests.append(request)
            return request

        # There are no pieces the peer can send us :(
        logger.info(f"{peer_id}: Has no pieces available to send.")
        return
