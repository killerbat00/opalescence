# -*- coding: utf-8 -*-

"""
Support for representing a .torrent file as a python class and creating a Torrent class (or .torrent file) from
a specified file or directory.
"""

import hashlib
import logging
import os
from collections import OrderedDict
from typing import NamedTuple, Union

from . import log_and_raise
from .bencode import Decoder, Encoder, DecodeError, EncodeError

logger = logging.getLogger(__name__)


class CreationError(Exception):
    """
    Raised when we encounter problems creating a torrent
    """
    pass


"""
An individual file within a torrent
"""
FileItem = NamedTuple("FileItem", [("path", str), ("size", int)])


def _pc(piece_string: bytes, *, length: int = 20, start: int = 0):
    """
    pieces a bytestring into pieces of specified length.
    by default pieces into 20byte (160 bit) pieces
    typically used to piece the hashlist contained within the torrent info's pieces key

    :param piece_string: string to piece
    :param length:       piece length
    :return:             generator expression yielding pieces of specified length
    """
    return (piece_string[0 + i:length + i] for i in range(start, len(piece_string), length))


def _validate_torrent_dict(decoded_dict: OrderedDict) -> bool:
    """
    Verifies a given decoded dictionary contains valid keys to describe a torrent we can do something with.
    Currently only checks for the minimum required torrent keys for torrents describing files and directories.
    If a dictionary contains all valid keys + extra keys, it will be validated.

    :param decoded_dict: dict representing bencoded .torrent file
    :return:             True if valid
    :raises:             CreationError
    """
    min_req_keys = [b"info", b"announce"]
    min_info_req_keys = [b"piece length", b"pieces", b"name"]
    min_files_req_keys = [b"length", b"path"]

    logger.debug("Validating torrent metainfo dictionary {d}".format(d=decoded_dict))

    dict_keys = list(decoded_dict.keys())

    if not dict_keys:
        log_and_raise("No valid keys in dictionary.", logger, CreationError)
    for key in min_req_keys:
        if key not in dict_keys:
            log_and_raise(f"Required key not found: {key}", logger, CreationError)

    info_keys = list(decoded_dict[b"info"].keys())

    if not info_keys:
        log_and_raise("No valid keys in info dictionary.", logger, CreationError)
    for key in min_info_req_keys:
        if key not in info_keys:
            log_and_raise(f"Required key not found: {key}", logger, CreationError)

    if len(decoded_dict[b"info"][b"pieces"]) % 20 != 0:
        log_and_raise("Piece length not a multiple of 20.", logger, CreationError)

    multiple_files = b"files" in info_keys

    if multiple_files:
        file_list = decoded_dict[b"info"][b"files"]

        if not file_list:
            log_and_raise("No file list.", logger, CreationError)
        for f in file_list:
            for key in min_files_req_keys:
                if key not in f.keys():
                    log_and_raise(f"Required key not found: {key}", logger, CreationError)
    else:
        if b"length" not in info_keys:
            log_and_raise("Required key not found: b'length'", logger, CreationError)
    # we made it!
    return True


class Torrent:
    """
    Wrapper around the torrent's metainfo. Doesn't include any download state.
    Torrents are created from files.

    Unsupported metainfo keys:
        encoding
    """

    def __init__(self):
        """
        Creates the lightweight representation of the torrent's metainfo and validates it
        """
        self.filename = None
        self.files = []
        self.meta_info = None
        self.info_hash = None
        self.pieces = []

    @classmethod
    def from_file(cls, filename: str) -> "Torrent":
        """
        Class method to create a torrent object from a .torrent metainfo file

        :param filename: path to .torrent file
        :raises CreationError:
        :return: Torrent instance
        """
        torrent = cls()
        torrent.filename = filename

        if not os.path.exists(torrent.filename):
            log_and_raise(f"Path does not exist {filename}", logger, CreationError)

        try:
            with open(torrent.filename, 'rb') as f:
                data = f.read()
                torrent.meta_info = Decoder(data).decode()
                _validate_torrent_dict(torrent.meta_info)
                info = Encoder(torrent.meta_info[b"info"]).encode()
                torrent.info_hash = hashlib.sha1(info).digest()
        except (EncodeError, DecodeError, IOError) as e:
            raise CreationError from e

        torrent._gather_files()
        torrent.pieces = list(_pc(torrent.meta_info[b"info"][b"pieces"]))
        logger.debug(f"Created a torrent from {filename}")
        return torrent

    @classmethod
    def from_path(cls, path: str, trackers: list, *,
                  comment: str = "", piece_size: int = 16384, private: bool = False) -> "Torrent":
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
        # if not self.base_location:
        #    logger.error("Unable to create_torrent torrent. No base path specified. This is a programmer error.")
        #    raise CreationError

        # base_path = self.base_location
        # left_in_piece = 0
        # next_pc = b""

        ## how can I make this better? it'd be nice to have a generator that
        ## abstracts away the file handling and just gives me the
        ## sha1 digest of a self.piece_length chunk of the file
        # for file_itm in self.files:
        #    with open(os.path.join(base_path, file_itm.path[0]), mode="rb") as f:
        #        current_pos = 0
        #        if left_in_piece > 0:
        #            next_pc += f.read(left_in_piece)
        #            self.pieces.append(hashlib.sha1(next_pc).digest().decode("ISO-8859-1"))
        #            current_pos = left_in_piece
        #            next_pc = b""
        #            left_in_piece = 0

        #        while True:
        #            if current_pos + self.piece_length <= file_itm.size:
        #                self.pieces.append(hashlib.sha1(f.read(self.piece_length)).digest().decode("ISO-8859-1"))
        #                current_pos += self.piece_length
        #            else:
        #                remainder_to_read = file_itm.size - current_pos
        #                if remainder_to_read < 0:
        #                    break
        #                next_pc += f.read(remainder_to_read)
        #                left_in_piece = self.piece_length - remainder_to_read
        #                break

    @classmethod
    def from_path(cls, path: str, trackers: list, *, comment: str = "",
                  piece_size: int = 16384, private: bool = False):
        """
        Creates a Torrent from a given path, gathering piece hashes from given files.
        Supports creating torrents from single files and multiple files.
        :param path:       path from which to create_torrent the Torrent
        :param trackers:   tracker url
        :param comment:    optional,torrent's comment,defaults to ""
        :param piece_size: optional,piece size,defaults to default 16384
        :param private:    optional,private torrent?,defaults to False
        :raises CreationError:
        :return:           Torrent object
        """
        raise NotImplementedError
        # files = []

        # if not os.path.exists(path):
        #    logger.error("Path does not exist {path}".format(path=path))
        #    raise CreationError

        ## gather files
        # if os.path.isfile(path):
        #    base_path = os.path.dirname(path)
        #    name = os.path.basename(path)
        #    size = os.path.getsize(path)
        #    files.append(FileItem(name, size))
        # elif os.path.isdir(path):
        #    base_path = path
        #    name = os.path.basename(path)

        #    # os.listdir returns paths in arbitrary order - possible danger here
        #    for f in os.listdir(path):
        #        size = os.path.getsize(os.path.join(path, f))
        #        fi = FileItem(f, size)
        #        fi.path = [fi.path]
        #        files.append(fi)
        # else:
        #    logger.error("Error creating Torrent instance. Invalid file keys in metainfo dictionary.")
        #    raise CreationError

        # logger.debug("Creating Torrent instance from path {path}".format(path=path))
        # torrent = cls(trackers, files, name, location=base_path, comment=comment, private=private,
        #              piece_length=piece_size)
        # logger.debug("Created Torrent instance from path {path} {torrent}".format(path=path, torrent=torrent.info_hash))
        # return torrent

    def to_file(self, output_filename: str):
        """
        Writes the torrent metainfo dictionary back to a .torrent file

        :param output_filename: The output filename of the torrent
        :raises CreationError:
        """
        if not output_filename:
            log_and_raise("Torrent must have an output filename.", logger, CreationError)

        with open(output_filename, 'wb+') as f:
            try:
                data = Encoder(self.meta_info).encode()
                f.write(data)
            except EncodeError as ee:
                raise CreationError from ee

        logger.debug(f"Wrote .torrent file: {output_filename}")

    def _gather_files(self):
        """
        Gathers the files located in the torrent
        """
        # TODO: filepaths are a list containing string elements that represent the path and filename
        if b"files" in self.meta_info[b"info"]:
            for f in self.meta_info[b"info"][b"files"]:
                path = None
                if isinstance(f[b"path"], list):
                    path = f[b"path"][0].decode("UTF-8")
                elif isinstance(f[b"path"], bytes):
                    path = f[b"path"].decode("UTF-8")
                self.files.append([FileItem(path, f[b"length"])])

        else:
            self.files.append(
                FileItem(self.meta_info[b"info"][b"name"].decode("UTF-8"), self.meta_info[b"info"][b"length"]))

    @property
    def multi_file(self) -> bool:
        """
        TODO: proper handling of multi-file torrents.
        For a single file torrent, the meta_info["info"]["name"] is the torrent's content's file basename and
                                       meta_info["info"]["length"] is its size

        For multiple file torrents, the meta_info["info"]["name"] is the torrent's content's directory name and
                                        meta_info["info"]["files"] contains the content's file basename
                                        meta_info["info"]["files"]["length"] is the file's size
                                        meta_info["info"]["length"] doesn't contribute anything here
        """
        return b"files" in self.meta_info[b"info"]

    @property
    def announce_urls(self) -> list:
        """
        The announce URL of the tracker.
        According to BEP 0012 (http://bittorrent.org/beps/bep_0012.html), if announce-list is present, it is used
        instead of announce.
        :return: a list of announce URLs for the tracker
        """
        urls = []
        if b"announce-list" in self.meta_info:
            # announce list is a list of lists of strings
            for url_list in self.meta_info[b"announce-list"]:
                inner_list = []
                for url in url_list:
                    inner_list.append(url.decode("UTF-8"))
                urls.append(inner_list)
        else:
            urls.append(self.meta_info[b"announce"].decode("UTF-8"))
        return urls

    @property
    def comment(self) -> Union[str, None]:
        """
        :return: the torrent's comment
        """
        if b"comment" in self.meta_info:
            return self.meta_info[b"comment"].decode("UTF-8")
        return

    @property
    def created_by(self) -> Union[str, None]:
        """
        :return: the torrent's creation program
        """
        if b"created by" in self.meta_info:
            return self.meta_info[b"created by"].decode("UTF-8")
        return

    @property
    def creation_date(self) -> Union[int, None]:
        """
        :return: the torrent's creation date
        """
        if b"creation date" in self.meta_info:
            return self.meta_info[b"creation date"]
        return

    @property
    def private(self) -> bool:
        """
        :return: True if the torrent is private, False otherwise
        """
        return bool(self.meta_info[b"info"].get(b"private", False))

    @property
    def piece_length(self) -> int:
        """
        :return: Length in bytes for each piece
        """
        return self.meta_info[b"info"][b"piece length"]

    @property
    def total_size(self) -> int:
        """
        :return: the total size of the file(s) in the torrent metainfo
        """
        return sum([f.size for f in self.files])

    @property
    def name(self) -> int:
        """
        :return: the torrent's name; either the single filename or the directory name.
        """
        return self.meta_info[b"info"][b"name"].decode("UTF-8")

    def __str__(self):
        """
        Returns a readable string representing the torrent

        :return: readable string of data
        """
        return "<Torrent object: {name} : {info_hash}>{".format(name=self.name, info_hash=self.info_hash)
