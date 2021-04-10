# -*- coding: utf-8 -*-

"""
Classes and APIs for file reading and writing.
"""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import logging
from pathlib import Path
from typing import Optional, BinaryIO

from ..utils import ensure_dir_exists

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
        Given a contiguous offset (as if all files were concatenated together), returns the corresponding file index
        and offset within the file.

        :param files: dictionary of `FileItem`s keyed by their index order
        :param offset: the contiguous offset to find the file for (as if all files were concatenated together)
        :return: (file_index, offset_within_file)
        """
        size_sum = 0
        for i, file in files.items():
            if offset - size_sum < file.size:
                file_offset = offset - size_sum
                return i, file_offset
            size_sum += file.size

    @staticmethod
    def file_for_piece(files: dict[int, FileItem], piece) -> tuple[int, int]:
        """
        Given a piece, returns the corresponding file index and offset within that file where the piece begins.

        :param files: dictionary of `FileItem`s keyed by their index order
        :param piece: `Piece` to find the file and offset for
        :return: (file_index, offset_within_file)
        """
        offset = piece.index * piece.mi_length
        return FileItem.file_for_offset(files, offset)


class FileWriter:

    def __init__(self, files: dict[int, FileItem]):
        self._files: dict[int, FileItem] = files
        self._lock = asyncio.Lock()
        self._fps: Optional[dict[int, BinaryIO]] = None
        self._task: Optional[asyncio.Task] = None

    def start(self, piece_queue: asyncio.Queue):
        """
        Starts this task that writes pieces received from piece_queue
        :param piece_queue:  piece queue where completed pieces are placed.
        """
        if self._task is None:
            self._task = asyncio.create_task(self.__write_task(piece_queue))

    def stop(self):
        """
        Stops the piece writing task.
        """
        if self._task:
            self._task.cancel()

    async def __write_task(self, piece_queue: asyncio.Queue):
        """
        Coroutine scheduled as a task via `start` that consumes completed
        pieces from the piece_queue and writes them to file.

        :param piece_queue: piece queue containing completed pieces
        """
        piece = None
        try:
            self.__open_files()

            while True:
                piece = await piece_queue.get()
                await self.__await_write(piece)
                piece_queue.task_done()
        except Exception as exc:
            logger.error("Encountered %s exception writing %s" % (type(exc).__name__, piece))
            raise
        finally:
            self.__close_files()

    def __open_files(self):
        """
        Opens/creates all the files that will be written, storing the open streams.
        """
        if self._files is None or len(self._files) == 0:
            return

        file = ""
        self._fps = {}
        try:
            for i, file in self._files.items():
                ensure_dir_exists(file.path)
                self._fps[i] = open(file.path, "wb+")
        except Exception:
            logger.error("Encountered exception opening %s" % file.path)
            raise

    def __close_files(self):
        """
        Closes all open file streams.
        """
        if self._fps is None:
            return

        for fp in self._fps.values():
            if not fp.closed:
                fp.close()

    async def __await_write(self, piece):
        """
        Writes the `Piece` to the file in an executor. Pieces can be written in any order.
        :param piece: piece to write.
        """
        if self._fps is None:
            self.__open_files()

        await self._lock.acquire()

        try:
            await asyncio.get_running_loop().run_in_executor(None,
                                                             functools.partial(self.__write_piece_data, piece))
            piece.mark_written()  # purge from memory
        except Exception as e:
            logger.exception(e)
            raise
        finally:
            self._lock.release()

    def __write_piece_data(self, piece):
        """
        Writes the piece's data to the appropriate file(s). Pieces can be written in any order.
        :param piece: piece to write.
        """
        assert piece.complete

        offset = piece.index * piece.mi_length
        data_to_write = piece.data
        while data_to_write:
            file_num, file_offset = FileItem.file_for_offset(self._files, offset)
            file = self._files[file_num]
            if file_num not in self._files:
                logger.error("Too much data and not enough files...")
                raise

            logger.info(f"Writing data to %s" % file.path)

            if file_offset + len(data_to_write) > file.size:
                data_for_file = data_to_write[:file.size - file_offset]
                data_to_write = data_to_write[file.size - file_offset:]
                offset += len(data_for_file)
            else:
                data_for_file = data_to_write
                data_to_write = None
            self.__write_data(data_for_file, file_num, file_offset)

    def __write_data(self, data_to_write, file_num, offset):
        """
        Writes data to the file in an executor so we don't block the main thread.
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
        except (OSError, Exception):
            logger.error("Encountered exception when writing to %s" % fp.name)
            raise
