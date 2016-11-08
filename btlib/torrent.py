# -*- coding: utf-8 -*-

"""
Support for representing a .torrent file as a python class and creating a Torrent class (or .torrent file) from
a specified file or directory.

author: brian houston morrow
"""

import hashlib
import logging
import os
from collections import OrderedDict

from .bencode import bdecode, bencode, DecodeError, EncodeError

logger = logging.getLogger('opalescence.' + __name__)


class CreationError(Exception):
    """
    Raised when we encounter problems creating a torrent
    """
    pass


class FileItem:
    """
    An individual file within a torrent.
    """

    def __init__(self, path: list, size: int):
        assert (len(path) > 0)
        # path can be a list
        self.path = os.path.join(*path).decode('utf-8')
        self.size = int(size)


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
    :return: True if valid
    :raises: CreationError
    """
    min_req_keys = [b"info", b"announce"]
    min_info_req_keys = [b"piece length", b"pieces", b"name"]
    min_files_req_keys = [b"length", b"path"]

    logger.debug("Validating torrent metainfo dictionary {d}".format(d=decoded_dict))

    dict_keys = list(decoded_dict.keys())

    if not dict_keys:
        logger.error("Unable to verify torrent dictionary. No valid keys in dictionary.")
        raise CreationError
    if len(dict_keys) != len(set(dict_keys)):
        logger.error("Unable to verify torrent dictionary. Duplicate keys in dictionary.")
        raise CreationError
    for key in min_req_keys:
        if key not in dict_keys:
            logger.error(
                "Unable to verify torrent dictionary. Required key not found: {required_key}".format(required_key=key))
            raise CreationError

    info_keys = list(decoded_dict[b"info"].keys())

    if not info_keys:
        logger.error("Unable to verify torrent info dictionary. No valid keys in info dictionary.")
        raise CreationError
    if len(info_keys) != len(set(info_keys)):
        logger.error("Unable to verify torrent info dictionary. Duplicate keys in dictionary.")
        raise CreationError
    for key in min_info_req_keys:
        if key not in info_keys:
            logger.error("Unable to verify torrent dictionary. \
            Required key not found in info dictionary: {required_key}".format(required_key=key))
            raise CreationError

        if len(decoded_dict[b"info"][b"pieces"]) % 20 != 0:
            logger.error("Unable to verify pieces bytestring. Length not a multiple of 20 bytes")
            raise CreationError

    multiple_files = b"files" in info_keys

    if multiple_files:
        file_list = decoded_dict[b"info"][b"files"]

        if not file_list:
            logger.error("Unable to verify torrent dictionary. No file list.")
            raise CreationError
        for f in file_list:
            for key in min_files_req_keys:
                if key not in f.keys():
                    logger.error("Unable to verify torrent dictionary. \
                    Required key not found in files dictionary for multiple files: {required_key}".format(
                        required_key=key))
                    raise CreationError
    else:
        if b"length" not in info_keys:
            logger.error("Required key not found in info dictionary for single file: {required_key}".format(
                required_key="length"))
            raise CreationError

    # we made it!
    return True


class Torrent:
    def __init__(self, torrent_file: str):
        """
        Creates a torrent object from a torrent file
        :param torrent_file: path to .torrent file
        :return:             Torrent representing the .torrent file
        :raises:             CreationError
        """
        self.filename = torrent_file
        self.files = []

        try:
            with open(torrent_file, mode='rb') as f:
                logger.debug("Creating torrent object from {file}".format(file=torrent_file))
                self.meta_info = bdecode(f.read())
                _validate_torrent_dict(self.meta_info)
                self.info_hash = hashlib.sha1(bencode(self.meta_info[b'info'])).digest()
                self.hexinfo_hash = hashlib.sha1(bencode(self.meta_info[b'info'])).hexdigest()
                self._collect_files()

            if self.meta_info is None:
                logger.error("Unable to create Torrent instance from empty file {file}.".format(file=torrent_file))
                raise CreationError
        except IOError as ioerr:
            logger.error("Unable to create Torrent instance. {file} does not exist.".format(file=torrent_file))
            raise CreationError from ioerr
        except (DecodeError, EncodeError) as e:
            logger.error("Unable to bdecode or bencode during creation {file}".format(file=torrent_file))
            raise CreationError from e
        logger.debug("Success")

    @property
    def total_file_size(self) -> int:
        return sum([f.size for f in self.files])

    @property
    def pieces(self) -> list:
        return list(_pc(self.meta_info[b'info'][b'pieces]']))

    @property
    def announce(self) -> str:
        return self.meta_info[b'announce'].decode('utf-8')

    def to_file(self, save_path: str):
        try:
            encoded_bytes = bencode(self.meta_info)
            with open(save_path, mode="wb") as f:
                logger.debug("Writing bencoded .torrent metainfo file to {path}".format(path=save_path))
                f.write(encoded_bytes)
        except (CreationError, EncodeError, IOError) as exc:
            logger.error("Unable to write .torrent to file {path}.".format(path=save_path))
            raise CreationError from exc
        else:
            logger.debug("Success")

    def _collect_files(self):
        if b'files' in self.meta_info[b'info']:
            self.files += [FileItem(f[b'path'], f[b'length']) for f in self.meta_info[b'info'][b'files']]
        else:
            self.files += FileItem(self.meta_info[b'info'][b'name'], self.meta_info[b'info'][b'length'])
