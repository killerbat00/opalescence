# -*- coding: utf-8 -*-

"""
Support for representing a .torrent file as a python class and
creating a Torrent class (or .torrent file) from a specified file or directory.
"""

from __future__ import annotations

__all__ = ['CreationError', 'FileItem', 'MetaInfoFile', 'FileWriter']

import asyncio
import dataclasses
import functools
import hashlib
import os
from collections import OrderedDict
from logging import getLogger
from pathlib import Path
from typing import List, Optional, Dict

from .bencode import Decoder, Encoder, DecodeError, EncodeError
from .messages import Piece
from ..utils import ensure_dir_exists

logger = getLogger(__name__)


class CreationError(Exception):
    """
    Raised when we encounter problems creating a torrent.
    """


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
        :param files: dictionary of `FileItem` keyed by their index order
        :param offset: the contiguous offset to find the file for (as if all files were concatenated together)
        :return: (file_num, file_offset)
        """
        size_sum = 0
        for i, file in files.items():
            if offset - size_sum < file.size:
                file_offset = offset - size_sum
                return i, file_offset
            size_sum += file.size


def _get_and_decode(d: dict, k: str, encoding="UTF-8"):
    return d.get(k, b'').decode(encoding)


def _pc(piece_string: bytes, *, length: int = 20, start: int = 0):
    """
    Pieces a bytestring into pieces of specified length.

    :param piece_string: string to piece
    :param length:       piece length
    :return:             generator expression yielding pieces
    """
    return (piece_string[0 + i:length + i] for i in
            range(start, len(piece_string), length))


def _validate_torrent_dict(decoded_dict: OrderedDict) -> bool:
    """
    Verifies a given decoded dictionary contains valid keys.

    Currently only checks for the minimum required torrent keys.
    If a dictionary contains all valid keys + extra keys, it will be validated.

    :param decoded_dict: dict representing bencoded .torrent file
    :return:             True if valid
    :raises:             CreationError
    """
    min_info_req_keys: List[str] = ["piece length", "pieces"]
    min_files_req_keys: List[str] = ["length", "path"]

    dict_keys: List = list(decoded_dict.keys())
    if not dict_keys:
        logger.error("No valid keys in dictionary.")
        raise CreationError

    if "info" not in dict_keys or \
        ("announce" not in dict_keys and
         "announce-list" not in dict_keys):
        logger.error(f"Required key not found.")
        raise CreationError

    info_keys: list = list(decoded_dict["info"].keys())
    if not info_keys:
        logger.error("No valid keys in info dictionary.")
        raise CreationError

    for key in min_info_req_keys:
        if key not in info_keys:
            logger.error(f"Required key not found: {key}")
            raise CreationError

    if len(decoded_dict["info"]["pieces"]) % 20 != 0:
        logger.error("Piece length not a multiple of 20.")
        raise CreationError

    multiple_files: bool = "files" in info_keys

    if multiple_files:
        file_list = decoded_dict["info"]["files"]

        if not file_list:
            logger.error("No file list.")
            raise CreationError

        for f in file_list:
            for key in min_files_req_keys:
                if key not in f.keys():
                    logger.error(f"Required key not found: {key}")
                    raise CreationError
    else:
        if "length" not in info_keys:
            logger.error("Required key not found: 'length'")
            raise CreationError

    # we made it!
    return True


class MetaInfoFile:
    """
    Represents the metainfo for a torrent. Doesn't include any download state.

    Unsupported metainfo keys:
        encoding
    """

    def __init__(self):
        self.files: Dict[int, FileItem] = {}
        self.meta_info: Optional[OrderedDict] = None
        self.info_hash: bytes = b''
        self.piece_hashes: list[bytes] = []
        self.pieces: list[Piece] = []
        self.destination: Optional[Path] = None

    def __str__(self):
        return f"{self.name}"

    def __repr__(self):
        return f"<MetaInfoFile: {self}>"

    @classmethod
    def from_file(cls, filename: Path, destination: Path) -> MetaInfoFile:
        """
        Class method to create a torrent object from a .torrent metainfo file

        :param filename: path to .torrent file
        :param destination: destination ptah for torrent
        :raises CreationError:
        :return: Torrent instance
        """
        logger.info(f"Creating a metainfo object from {filename}")
        torrent: MetaInfoFile = cls()

        if not os.path.exists(filename):
            logger.error(f"Path does not exist {filename}")
            raise CreationError

        torrent.destination = destination

        try:
            with open(filename, 'rb') as f:
                data: bytes = f.read()
                torrent.meta_info = Decoder(data).decode()

            if not torrent.meta_info or not isinstance(torrent.meta_info, OrderedDict):
                logger.error(f"Unable to create torrent object. No metainfo decoded from file.")
                raise CreationError

            _validate_torrent_dict(torrent.meta_info)
            info: bytes = Encoder(torrent.meta_info["info"]).encode()
            torrent.info_hash = hashlib.sha1(info).digest()

            torrent._gather_files()
            torrent._collect_pieces()

        except (EncodeError, DecodeError, IOError, Exception) as e:
            logger.debug(f"Encountered {type(e).__name__} in MetaInfoFile.from_file")
            raise CreationError from e

        return torrent

    @classmethod
    def from_path(cls, path: str, trackers: list, *,
                  comment: str = "", piece_size: int = 32768,
                  private: bool = False) -> MetaInfoFile:
        """
        Class method to create a torrent object from a specified filepath. The path can be
        a single file or a directory

        :param path:
        :param trackers:
        :param comment:
        :param piece_size:
        :param private:
        :raises CreationError:
        """
        raise NotImplementedError

    def to_file(self, output_filename: str):
        """
        Writes the torrent metainfo dictionary back to a .torrent file

        :param output_filename: The output filename of the torrent
        :raises CreationError:
        """
        logger.info(f"Writing .torrent file: {output_filename}")

        if not output_filename:
            logger.error("No output filename provided.")
            raise CreationError

        with open(output_filename, 'wb+') as f:
            try:
                data: bytes = Encoder(self.meta_info).encode()
                f.write(data)
            except EncodeError as ee:
                logger.error(f"Encounter {type(ee).__name__} while writing metainfo file {output_filename}.")
                raise CreationError from ee

    def check_existing_pieces(self) -> None:
        """
        Checks the existing files and disk and verifies their piece
        hashes, collecting their data as necessary.
        """
        assert self.files

        fps = {}
        try:
            for i, file in self.files.items():
                fps[i] = open(file.path, "rb") if file.exists else None

            for i, piece in enumerate(self.pieces):
                file_index, file_offset = FileItem.file_for_offset(self.files, i * piece.length)
                if not self.files[file_index].exists:
                    continue

                fp = fps[file_index]
                if fp is None:
                    continue

                if file_offset + piece.length > self.files[file_index].size:
                    if file_index + 1 > len(self.files) or fps[file_index + 1] is None:
                        continue

                    f1len = self.files[file_index].size - file_offset
                    f2len = piece.length - f1len
                    piece_data = fp.read(f1len)

                    fp = fps[file_index + 1]
                    piece_data += fp.read(f2len)
                else:
                    fp.seek(file_offset)
                    piece_data = fp.read(piece.length)

                if len(piece_data) == piece.length and piece.hash() == self.piece_hashes[i]:
                    piece.data = piece_data
                    piece.mark_complete()
        finally:
            for fp in fps.values():
                if fp is not None:
                    fp.close()

    def _gather_files(self) -> None:
        """
        Gathers the files located in the torrent

        For a single file torrent,
            the meta_info["info"]["name"] is the torrent's
            content's file basename and meta_info["info"]["length"] is its size

        For multiple file torrents,
            the meta_info["info"]["name"] is the torrent's
            content's directory name and
            meta_info["info"]["files"] contains the content's file basename
            meta_info["info"]["files"]["length"] is the file's size
            meta_info["info"]["length"] doesn't contribute anything here
        """
        logger.info(f"Gathering files for .torrent: {self}")

        if self.multi_file:
            file_list = self.meta_info["info"]["files"]
            if not file_list:
                logger.error("No file list.")
                raise CreationError
            offset = 0
            for i, f in enumerate(file_list):
                length = f.get("length", 0)
                path = Path("/".join([x.decode("UTF-8") for x in f.get("path", [])]))
                filepath = self.destination / path
                exists = filepath.exists()
                self.files[i] = FileItem(filepath, length, offset, exists)
                offset += length
        else:
            filepath = self.destination / Path(_get_and_decode(self.meta_info["info"], "name"))
            exists = filepath.exists()
            length = self.meta_info["info"].get("length", 0)
            self.files[0] = FileItem(filepath, length, 0, exists)

    def _collect_pieces(self) -> None:
        """
        Collects the piece hashes from the metainfo file and
        creates `Piece` objects for each piece.
        """
        logger.info(f"Collecting pieces and hashes for .torrent: {self}")
        self.piece_hashes = list(_pc(self.meta_info["info"]["pieces"]))

        num_pieces = len(self.piece_hashes)
        for pc in range(num_pieces):
            piece_length = self.piece_length
            if pc == num_pieces - 1:
                piece_length = self.last_piece_length

            self.pieces.append(Piece(pc, piece_length))

    @property
    def multi_file(self) -> bool:
        """
        Returns True if this is a torrent with multiple files.
        """
        return "files" in self.meta_info["info"]

    @property
    def announce_urls(self) -> List[List[str]]:
        """
        The announce URL of the tracker.
        According to BEP 0012 (http://bittorrent.org/beps/bep_0012.html),
        if announce-list is present, it is used instead of announce.
        :return: a list of announce URLs for the tracker
        """
        if "announce-list" in self.meta_info:
            return [[x.decode("UTF-8") for x in url_list] for url_list in self.meta_info["announce-list"]]
        return [[_get_and_decode(self.meta_info, "announce")]]

    @property
    def comment(self) -> str:
        """
        :return: the torrent's comment
        """
        return _get_and_decode(self.meta_info, "comment")

    @property
    def created_by(self) -> Optional[str]:
        """
        :return: the torrent's creation program
        """
        return _get_and_decode(self.meta_info, "created by")

    @property
    def creation_date(self) -> Optional[int]:
        """
        :return: the torrent's creation date
        """
        if "creation date" in self.meta_info:
            return self.meta_info["creation date"]

    @property
    def private(self) -> bool:
        """
        :return: True if the torrent is private, False otherwise
        """
        return bool(self.meta_info["info"].get("private", False))

    @property
    def piece_length(self) -> int:
        """
        :return: Nominal length in bytes for each piece
        """
        return self.meta_info["info"]["piece length"]

    @property
    def last_piece_length(self) -> int:
        """
        :return: Length in bytes of the last piece of the torrent
        """
        return self.total_size - ((self.num_pieces - 1) * self.piece_length)

    @property
    def total_size(self) -> int:
        """
        :return: the total size of the file(s) in the torrent metainfo
        """
        return sum([f.size for f in self.files.values()])

    @property
    def present(self) -> int:
        """
        :return: the number of bytes present
        """
        lengths = []
        for i, piece in enumerate(self.pieces):
            if not piece.complete:
                continue
            if i == self.num_pieces - 1:
                lengths.append(self.last_piece_length)
            else:
                lengths.append(self.piece_length)
        return sum(lengths)

    @property
    def remaining(self) -> int:
        """
        :return: remaining number of bytes
        """
        lengths = []
        for i, piece in enumerate(self.pieces):
            if piece.complete:
                continue
            if i == self.num_pieces - 1:
                lengths.append(self.last_piece_length)
            else:
                lengths.append(self.piece_length)
        return sum(lengths)

    @property
    def complete(self) -> bool:
        return self.remaining == 0

    @property
    def num_pieces(self) -> int:
        """
        :return: the total number of pieces in the torrent
        """
        return len(self.piece_hashes)

    @property
    def name(self) -> str:
        """
        :return: the torrent's name; either the single filename or the directory
        name.
        """
        return _get_and_decode(self.meta_info["info"], "name")


class FileWriter:

    def __init__(self, files: Dict[int, FileItem], destination: Path):
        self._files: Dict[int, FileItem] = files
        self._total_size = sum([file.size for file in self._files.values()])
        self._base_dir = destination
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

        offset = piece.index * piece.length
        data_to_write = piece.data
        while data_to_write:
            file_num, file_offset = FileItem.file_for_offset(self._files, offset)
            file = self._files[file_num]
            if file_num >= len(self._files):
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
