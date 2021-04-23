# -*- coding: utf-8 -*-

"""
Classes and APIs for file reading and writing.
"""

from __future__ import annotations

__all__ = ['FileItem', 'FileWriterTask']

import asyncio
import dataclasses
import functools
import logging
from pathlib import Path
from typing import Optional, BinaryIO


logger = logging.getLogger(__name__)


@dataclasses.dataclass
class FileItem:
    """
    An individual file within a torrent.
    """
    path: Path
    size: int
    offset: int
    exists: bool

    @staticmethod
    def file_for_offset(files: dict[int, FileItem], offset: int) -> tuple[int, int]:
        """
        Given a contiguous offset (as if all files were concatenated together),
        returns the corresponding file index and offset within the file.

        :param files: dictionary of `FileItem`s keyed by their index order
        :param offset: the contiguous offset to find the file for
                       (as if all files were concatenated together)
        :return: (file_index, offset_within_file)
        """
        size_sum = 0
        for i, file in files.items():
            if offset - size_sum < file.size:
                file_offset = offset - size_sum
                return i, file_offset
            size_sum += file.size


class FileWriter:

    def __init__(self, torrent):
        self._files: dict[int, FileItem] = torrent.files
        self._piece_length = torrent.piece_length
        self._lock = asyncio.Lock()
        self._fps: Optional[dict[int, BinaryIO]] = None

    def _open_files(self):
        """
        Opens/creates all the files that will be written and
        stores the open streams for later use.
        """
        if self._files is None or len(self._files) == 0:
            return

        file = ""
        self._fps = {}
        try:
            for i, file in self._files.items():
                file.path.parent.mkdir(parents=True, exist_ok=True)
                self._fps[i] = open(file.path, "wb+")
        except Exception as exc:
            logger.error("Encountered %s exception opening %s" % (type(exc).__name__,
                                                                  file.path))
            raise

    def _close_files(self):
        """
        Closes all open file streams.
        """
        if self._fps is None:
            return

        for fp in self._fps.values():
            if not fp.closed:
                fp.close()

    async def _await_write(self, piece):
        """
        Schedules and awaits for the task in the executor responsible
        for writing the piece. Marks the piece complete on success.

        :param piece: piece to write
        """
        if self._fps is None:
            self._open_files()

        await self._lock.acquire()

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, functools.partial(
                self._write_piece_data, piece))
            piece.mark_written()  # purge from memory
        except Exception as e:
            logger.exception(e)
            raise
        finally:
            self._lock.release()

    def _write_piece_data(self, piece):
        """
        Writes the piece's data to the appropriate file(s).
        Pieces can be written in any order.

        :param piece: piece to write
        """
        assert piece.complete

        offset = piece.index * self._piece_length
        data_to_write = piece.data
        while data_to_write:
            file_num, file_offset = FileItem.file_for_offset(self._files, offset)
            file = self._files[file_num]
            if file_num not in self._files:
                logger.error("Too much data and not enough file...")
                raise

            logger.info(f"Writing data to %s" % file.path)

            if file_offset + len(data_to_write) > file.size:
                data_for_file = data_to_write[:file.size - file_offset]
                data_to_write = data_to_write[file.size - file_offset:]
                offset += len(data_for_file)
            else:
                data_for_file = data_to_write
                data_to_write = None
            self._write_data(data_for_file, file_num, file_offset)

    def _write_data(self, data_to_write, file_num, offset):
        """
        Writes data to the file in an executor so the main thread isn't blocked.

        :param data_to_write: data to write to file
        :param file_num: file index in self._fps to write to
        :param offset: Offset into the file to begin writing this data
        """
        fp = self._fps[file_num]
        try:
            if fp.closed:
                raise OSError
            fp.seek(offset, 0)
            fp.write(data_to_write)
        except Exception:
            logger.error("Encountered exception when writing to %s" % fp.name)
            raise


class FileWriterTask(FileWriter):
    """
    This subclass of `FileWriter` accepts a queue where completed pieces are sent and
    handles writing those pieces to disk.
    """

    def __init__(self, torrent, piece_queue: asyncio.Queue):
        super().__init__(torrent)
        self.task: Optional[asyncio.Task] = None
        self._queue: asyncio.Queue = piece_queue

    def start(self):
        """
        Starts the task that writes pieces received from piece_queue.
        """
        if self.task is None:
            self.task = asyncio.create_task(self._write_pieces())

    def stop(self):
        """
        Stops the piece writing task.
        """
        if self.task:
            self.task.cancel()

    async def _write_pieces(self):
        """
        Coroutine scheduled as a task via `start` that consumes completed
        pieces from the piece_queue and writes them to file.
        """
        piece = None
        try:
            while True:
                piece = await self._queue.get()
                asyncio.create_task(self._await_write(piece))
                self._queue.task_done()
        except Exception as exc:
            logger.error("Encountered %s exception writing %s" %
                         (type(exc).__name__, piece))
            self.task.cancel()
        finally:
            self._close_files()
