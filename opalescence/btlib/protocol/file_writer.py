# -*- coding: utf-8 -*-

"""
Handles writing completed pieces to their appropriate files on disk.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from typing import Optional, BinaryIO

from .messages import Piece
from .metainfo import FileItem
from ..utils import ensure_dir_exists

logger = logging.getLogger(__name__)


class FileWriter:

    def __init__(self, files: dict[int, FileItem]):
        self._files: dict[int, FileItem] = files
        self._total_size = sum([file.size for file in self._files.values()])
        self._lock = asyncio.Lock()
        self._fps: Optional[dict[int, BinaryIO]] = None

    def __enter__(self):
        """
        Facilitates use as a context manager, opening file streams if necessary.
        """
        if self._fps is None:
            self._open_files(self._files)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exits the context manager, closing files if possible.
        Propagates any exception that caused this context to be exited.
        """
        try:
            self._close_files()

            if exc_type is None and exc_val is None and exc_tb is None:
                return True
        except Exception:
            pass
        return False

    def _close_files(self):
        """
        Closes all open file streams.
        """
        if self._fps is None:
            return

        for fp in self._fps.values():
            if not fp.closed:
                fp.close()

    def _open_files(self, files: dict[int, FileItem]):
        """
        Opens/creates all the files that will be written, storing the open streams.
        :param files: dictionary of `FileItem`s this `FileWriter` is writing.
        """
        file = ""
        self._fps = {}
        try:
            for i, file in files.items():
                ensure_dir_exists(file.path)
                self._fps[i] = open(file.path, "wb+")
        except Exception:
            logger.error(f"Encountered exception opening {file.path}")
            raise

    def _write_data(self, data_to_write, file_num, offset):
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
            logger.error(f"Encountered exception when writing to {fp.name}")
            raise

    async def write(self, piece: Piece):
        """
        Writes the `Piece` to the file in an executor. Pieces can be written in any order.
        :param piece: piece to write.
        """
        await self._lock.acquire()

        try:
            await asyncio.get_running_loop().run_in_executor(None,
                                                             functools.partial(self._write, piece))
            piece.mark_complete()
        except Exception as e:
            logger.exception(e)
            raise
        finally:
            self._lock.release()

    def _write(self, piece: Piece):
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

            logger.info(f"Writing data to {file.path}")

            if file_offset + len(data_to_write) > file.size:
                data_for_file = data_to_write[:file.size - file_offset]
                data_to_write = data_to_write[file.size - file_offset:]
                offset += len(data_for_file)
            else:
                data_for_file = data_to_write
                data_to_write = None
            self._write_data(data_for_file, file_num, file_offset)
