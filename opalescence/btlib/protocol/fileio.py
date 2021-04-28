# -*- coding: utf-8 -*-

"""
Classes and APIs for file reading and writing.
"""

from __future__ import annotations

__all__ = ['FileItem', 'FileWriter']

import dataclasses
import logging
from pathlib import Path
from typing import Optional, BinaryIO

from .errors import FileWriterError

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

    def __init__(self, files: dict[int, FileItem], piece_length: int):
        self._files: dict[int, FileItem] = files
        self._piece_length = piece_length
        self._fps: Optional[dict[int, BinaryIO]] = None

    def open_files(self):
        """
        Opens/creates all the files that will be written and
        stores the open streams for later use.
        """
        if self._files is None or len(self._files) == 0 or self._fps is not None:
            return

        file = ""
        self._fps = {}
        try:
            for i, file in self._files.items():
                if not file.exists:
                    file.path.parent.mkdir(parents=True, exist_ok=True)
                    self._fps[i] = open(file.path, 'wb+')
                else:
                    self._fps[i] = open(file.path, 'ab')
        except Exception as exc:
            logger.error("Encountered %s exception opening %s" % (type(exc).__name__,
                                                                  file.path))
            raise FileWriterError from exc

    def close_files(self):
        """
        Closes all open file streams.
        """
        if self._fps is None:
            return

        for fp in self._fps.values():
            if not fp.closed:
                fp.close()

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
                raise FileWriterError

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

        :raises: Any Exception received on writing.
        """
        assert self._fps is not None

        fp = self._fps[file_num]
        try:
            if fp.closed:
                raise FileWriterError("file already closed: %s" % fp.name)
            fp.seek(offset, 0)
            fp.write(data_to_write)
        except Exception as exc:
            logger.error("Encountered exception when writing to %s" % fp.name)
            raise FileWriterError from exc
