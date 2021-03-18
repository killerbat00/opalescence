# -*- coding: utf-8 -*-

"""
Contains the logic for requesting pieces, as well as that for writing them to disk.
"""

__all__ = ['PieceRequester', 'FileWriter']

import asyncio
import dataclasses
import functools
import hashlib
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Callable, Optional, BinaryIO

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

    def __init__(self, torrent: MetaInfoFile, save_dir: Path):
        self._files: Dict[int, FileItem] = dict(torrent.files)
        self._total_size = sum([file.size for file in self._files.values()])
        self._torrent = torrent
        self._base_dir = save_dir
        self._lock = asyncio.Lock()
        # self._fds = self._open_files()

    def _open_files(self) -> List[BinaryIO]:
        logger.info(f"Opening files for {self._torrent}")
        fds = []
        try:
            for file in self._files.values():
                p = Path(self._base_dir) / file.path
                ensure_dir_exists(p)
                fd = open(p, "w+b")
                fd.truncate(file.size)
                fds.append(fd)
        except (OSError, Exception):
            logger.exception(f"Encountered exception when opening files.", exc_info=True)
            for f in fds:
                f.close()
            raise
        return fds

    def close_files(self):
        try:
            pass
            # for fd in self._fds:
            #    fd.close()
        except (OSError, Exception):
            pass

    def _file_for_offset(self, offset: int):
        """
        :param offset: the contiguous offset of the piece (as if all files were concatenated together)
        :return: (file_num, FileItem, file_offset)
        """
        size_sum = 0
        for i, file in self._files.items():
            if offset - size_sum < file.size:
                file_offset = offset - size_sum
                return i, file, file_offset
            size_sum += file.size

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

        total_size = sum([file.size for file in self._torrent.files.values()])

        offset = piece.index * self._torrent.piece_length
        data_to_write = piece.data
        while data_to_write:
            file_num, file, file_offset = self._file_for_offset(offset)
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

    def __init__(self, torrent: MetaInfoFile, writer, torrent_complete_cb, stats):
        self.torrent = torrent
        self.piece_peer_map: Dict[int, Set[str]] = {i: set() for i in range(self.torrent.num_pieces)}
        self.peer_piece_map: Dict[str, Set[int]] = defaultdict(set)
        self.downloaded_pieces: Dict[int, Piece] = {}
        self.downloading_pieces: Dict[int, Piece] = {}
        self.pending_requests: List[Request] = []
        self.writer = writer
        self.torrent_complete_cb: Callable = torrent_complete_cb
        self.stats = stats

    @property
    def complete(self):
        return len(self.downloaded_pieces) == self.torrent.num_pieces

    def add_available_piece(self, peer_id: str, index: int) -> None:
        """
        Called when a peer advertises it has a piece available.

        :param peer_id: The peer that has the piece
        :param index: The index of the piece
        """
        self.piece_peer_map[index].add(peer_id)
        self.peer_piece_map[peer_id].add(index)

    def add_peer_bitfield(self, peer_id: str, bitfield: bitstring.BitArray) -> None:
        """
        Updates our dictionary of pieces with data from the remote peer

        :param peer_id:  The peer who sent this bitfield, kept around
                         to know where to eventually send requests
        :param bitfield: The bitfield sent by the peer
        """
        for i, b in enumerate(bitfield):
            if b:
                self.add_available_piece(peer_id, i)

    def remove_pending_requests_for_peer(self, peer_id: str) -> None:
        """
        Removes all pending requests for a peer.
        Called when the peer disconnects or chokes us.

        :param peer_id: peer whose pending requests ew should remove
        """
        for request in self.pending_requests:
            if request.peer_id == peer_id:
                self.pending_requests.remove(request)

    def remove_peer(self, peer_id: str) -> None:
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

    async def received_block(self, peer_id: str, block: Block) -> Optional[Piece]:
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

        # Remove the pending requests for this block if there are any
        r = Request(block.index, block.begin)
        for i, rr in enumerate(self.pending_requests):
            if r == rr:
                del self.pending_requests[i]
                break

        if block.index in self.downloaded_pieces:
            logger.debug(f"Disregarding. I already have {block}")
            return

        self.stats["downloaded"] += len(block.data)
        self.stats["left"] -= len(block.data)
        piece = self.downloading_pieces.get(block.index)
        if piece:
            piece.add_block(block)
        else:
            piece_length = self.torrent.last_piece_length if block.index == self.torrent.num_pieces - 1 else \
                self.torrent.piece_length
            piece = Piece(block.index, piece_length)
            piece.add_block(block)
            logger.info(f"Downloaded new piece: {piece}")
            self.downloading_pieces[piece.index] = piece

        if piece.complete:
            return await self.piece_complete(piece)

    async def piece_complete(self, piece: Piece):
        piece_hash = hashlib.sha1(piece.data).digest()
        if piece_hash != self.torrent.piece_hashes[piece.index]:
            logger.error(
                f"Hash for received piece {piece.index} doesn't match\n"
                f"Received: {piece_hash}\n"
                f"Expected: {self.torrent.piece_hashes[piece.index]}")
            piece.reset()
            return piece
        else:
            logger.info(f"Completed piece received: {piece}")

            self.downloaded_pieces[piece.index] = piece
            if piece.index in self.downloading_pieces:
                del self.downloading_pieces[piece.index]

            # remove all pending requests for this piece
            for i, pending_request in enumerate(self.pending_requests):
                if pending_request.index == piece.index:
                    del self.pending_requests[i]

            await self.writer.write(piece)

            if self.complete:
                self.torrent_complete_cb()

    def next_request_for_peer(self, peer_id: str) -> Optional[Request]:
        """
        Finds the next request that we can send to the peer.

        Works like this:
        1. Check the incomplete pieces we are downloading to see if peer has one
        2. If there are no incomplete pieces the peer can give us, request
           the next piece it can give us.
        3. Look through the available pieces to find one the peer has
        4. If none available, the peer is useless to us.
        :param peer_id: peer requesting a piece
        :return: piece's index or None if not available
        """
        if self.complete:
            return

        if len(self.pending_requests) >= 50:
            logger.error(f"Too many currently pending requests.")
            return

        # Find the next piece index in the pieces we are downloading that the
        # peer said it could send us
        for i in self.peer_piece_map[peer_id]:
            next_available = False
            if i in self.downloaded_pieces:
                continue
            if i not in self.downloading_pieces:
                piece_length = self.torrent.last_piece_length if i == self.torrent.num_pieces - 1 else \
                    self.torrent.piece_length
                piece = Piece(i, piece_length)
                logger.info(f"{peer_id}: Adding new piece to downloading pieces: {piece}")
                self.downloading_pieces[piece.index] = piece
                size = min(piece.length, Request.size)
                request = Request(i, piece.next_block, size, peer_id)
                logger.info(f"{peer_id}: Successfully got request {request}.")
                self.pending_requests.append(request)
                return request

            else:
                piece = self.downloading_pieces[i]
                nb = piece.next_block
                size = min(piece.length - nb, Request.size)
                if nb + size > piece.length:
                    logger.info(f"{peer_id}: Can't request any more blocks for piece {piece.index}. Moving "
                                f"along...")
                    continue  # loop over peer_piece_map
                request = Request(piece.index, nb, size, peer_id)
                while request in self.pending_requests:
                    logger.info(f"{peer_id}: We have an outstanding request for {request}")
                    if nb + size > piece.length:
                        logger.debug(f"{peer_id}: Can't request any more blocks for piece {piece.index}. Moving "
                                     f"along...")
                        next_available = True
                        break
                    else:
                        nb = nb + size
                        size = min(piece.length - nb, Request.size)
                        if size <= 0:
                            return
                        request = Request(piece.index, nb, size, peer_id)
                if next_available:
                    continue
                logger.info(f"{peer_id}: Successfully got request {request}.")
                self.pending_requests.append(request)
                return request

        # There are no pieces the peer can send us :(
        logger.info(f"{peer_id}: Has no pieces available to send.")
        return
