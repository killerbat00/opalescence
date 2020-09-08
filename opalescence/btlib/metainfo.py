# -*- coding: utf-8 -*-

"""
Support for representing a .torrent file as a python class and
creating a Torrent class (or .torrent file) from a specified file or directory.
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections import OrderedDict
from pathlib import Path
from typing import NamedTuple, List, Optional

from btproto import Decoder, Encoder, DecodeError, EncodeError

logger = logging.getLogger(__name__)


class CreationError(Exception):
    """
    Raised when we encounter problems creating a torrent.
    """


class FileItem(NamedTuple):
    """
    An individual file within a torrent.
    """
    path: Path
    size: int


def _get_and_decode(d: dict, k: str):
    return d.get(k, b'').decode("UTF-8")


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

    logger.debug(
        "Validating torrent metainfo dictionary {d}".format(d=decoded_dict))

    dict_keys: List = list(decoded_dict.keys())
    if not dict_keys:
        logger.error("No valid keys in dictionary.")
        raise CreationError

    if "info" not in dict_keys or \
        "announce" not in dict_keys or \
        "announce-list" not in dict_keys:
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
        self.files: List[FileItem] = []
        self.meta_info: Optional[OrderedDict] = None
        self.info_hash: bytes = b''
        self.piece_hashes: List[bytes] = []

    def __str__(self):
        return f"{self.name} <{self.info_hash}>"

    def __repr__(self):
        return f"<MetaInfoFile: {self}"

    @classmethod
    def from_file(cls, filename: str) -> MetaInfoFile:
        """
        Class method to create a torrent object from a .torrent metainfo file

        :param filename: path to .torrent file
        :raises CreationError:
        :return: Torrent instance
        """
        logger.debug(f"Creating a metainfo object from {filename}")
        torrent: MetaInfoFile = cls()

        if not os.path.exists(filename):
            logger.error(f"Path does not exist {filename}")
            raise CreationError

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
            torrent.piece_hashes = list(_pc(torrent.meta_info["info"]["pieces"]))
        except (EncodeError, DecodeError, IOError, Exception) as e:
            logger.error(f"Encountered error creating MetaInfoFile.")
            logger.info(e, exc_info=True)
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

    def _collect_pieces(self):
        """
        The real workhorse of torrent creation.
        Reads through all specified files, breaking them into piece_length chunks and storing their 20byte sha1
        digest into the pieces list
        :raises CreationError:
        """
        raise NotImplementedError

    def to_file(self, output_filename: str):
        """
        Writes the torrent metainfo dictionary back to a .torrent file

        :param output_filename: The output filename of the torrent
        :raises CreationError:
        """
        logger.debug(f"Writing .torrent file: {output_filename}")

        if not output_filename:
            logger.error("No output filename provided.")
            raise CreationError

        with open(output_filename, 'wb+') as f:
            try:
                data: bytes = Encoder(self.meta_info).encode()
                f.write(data)
            except EncodeError as ee:
                logger.error("Unable to write metainfo file {output_filename}")
                logger.info(ee, exc_info=True)
                raise CreationError from ee

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
        logger.debug(f"Gathering files for .torrent: {self}")

        if self.multi_file:
            file_list = self.meta_info["info"]["files"]
            if not file_list:
                logger.error("No file list.")
                raise CreationError
            for f in file_list:
                length = f.get("length", 0)
                path = Path("/".join([x.decode("UTF-8") for x in f.get("path", [])]))
                self.files.append(FileItem(path, length))
        else:
            self.files.append(
                FileItem(Path(_get_and_decode(self.meta_info["info"], "name")),
                         self.meta_info["info"]["length"]))

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
        # TODO: Properly shuffle the list (either here or in the tracker)
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
        return sum([f.size for f in self.files])

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
