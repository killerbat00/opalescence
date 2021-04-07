# -*- coding: utf-8 -*-

"""
Handles writing completed pieces to their appropriate files on disk.
"""

import asyncio
import functools
import logging
from pathlib import Path
from typing import Dict

from .messages import Piece
from .metainfo import FileItem
from ..utils import ensure_dir_exists

logger = logging.getLogger(__name__)


class FileWriter:

    def __init__(self, files: Dict[int, FileItem], destination: Path):
        self._files: Dict[int, FileItem] = files
        self._total_size = sum([file.size for file in self._files.values()])
        self._base_dir = destination
        self._lock = asyncio.Lock()

    def _write_data(self, data_to_write, file, offset):
        """
        Writes data to the file in an executor so we don't block the main thread.
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
            logger.error(f"Encountered exception when writing to {p}")
            raise

    async def write(self, piece: Piece):
        """
        Writes the piece to the file in an executor.
        :param piece: piece to write.
        """
        await self._lock.acquire()

        try:
            await asyncio.get_running_loop().run_in_executor(None,
                                                             functools.partial(self._write, piece))
            piece.mark_complete()
        except Exception:
            raise
        finally:
            self._lock.release()

    def _write(self, piece: Piece):
        """
        Writes the piece's data to the appropriate file(s).
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

            if file_offset + len(data_to_write) > file.size:
                data_for_file = data_to_write[:file.size - file_offset]
                data_to_write = data_to_write[file.size - file_offset:]
                offset += len(data_for_file)
            else:
                data_for_file = data_to_write
                data_to_write = None
            self._write_data(data_for_file, file, file_offset)
