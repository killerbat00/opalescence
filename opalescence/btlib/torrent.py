# -*- coding: utf-8 -*-

"""
Support for representing a .torrent file as a python class and creating a Torrent class (or .torrent file) from
a specified file or directory.

author: brian houston morrow
"""

import hashlib
import logging
import os
import time
from collections import OrderedDict
from typing import NamedTuple, List

from .bencode import Decoder, Encoder, DecodeError, EncodeError
from .tracker import TrackerInfo

logger = logging.getLogger('opalescence.' + __name__)


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
    """
    Wrapper around the torrent's metainfo. Doesn't include any download state.
    Torrents are created from files.
    """

    def __init__(self, filename: str):
        """
        Creates the lightweight representation of the torrent's metainfo and validates it

        :param filename: .torrent metainfo filepath
        :raises CreationError:
        """
        self.filename = filename
        self.files = []
        self.meta_info = None
        self.info_hash = None

        if not os.path.exists(self.filename):
            logger.error(f"Path does not exist {self.filename}")
            raise CreationError

        with open(self.filename, 'rb') as f:
            data = f.read()
            self.meta_info = Decoder().decode(data)
            _validate_torrent_dict(self.meta_info)
            info = Encoder().bencode(self.meta_info[b"info"]).encode()
            self.info_hash = hashlib.sha1(info).digest()

    @classmethod
    def create_from_path(cls, *args):
        """
        Creates a torrent metainfo from a given path. The path can be to a single file or
        multiple files. The torrent representation can later be written to a file.

        :param args:
        :return: Torrent instance
        """
        pass

    def _gather_files(self):
        """
        Gathers the files located in the torrent
        """
        pass

    @property
    def announce_list(self, limit=1) -> List[str]:
        """
        The announce URL of the tracker including the announce-list if it's a key in the metainof dictionary
        :return: a list of accounce URLs for the tracker
        """
        urls = [self.meta_info.get(b"announce")]
        if b"announce-list" in self.meta_info:
            urls += self.meta_info.get[b"announce-list"][0]
        return urls

    def __str__(self):
        """
        Returns a readable string representing the torrent

        :return: readable string of data
        """
        return "<Torrent object: {name} : {info_hash}>{".format(name=self.name, info_hash=self.info_hash)



class Torrent(object):
    """
    Relevant metadata for a torrent
    """

    def __init__(self, tracker_urls: list, files: list, name: str, location: str, *, comment: str = "",
                 created_by: str = "Opalescence", creation_date: int = int(time.time()), pieces: list = None,
                 piece_length: int = 16384, private: bool = False, info_hash: str = ""):
        """
        Initializes a torrent. Not typically used alone, instead, use Torrent.from_file or Torrent.from_path
        :param tracker_urls:  list of tracker urls
        :param files:         list of files
        :param name:          torrent's name
        :param location:      torrent's dirpath (either .torrent's location or creation location)
        :param comment:       optional,defaults to ""
        :param created_by:    optional,defaults to opalescense
        :param creation_date: optional,defaults to time of instantiation
        :param pieces:        optional,defaults to None
        :param piece_length:  optional,defaults to 16384 bytes; piece length in bytes
        :param private:       optional,defaults to False
        :param info_hash:     optional,defaults to ""
        :raises:              CreationError
        """
        if pieces is None:
            pieces = []

        self.tracker_urls = tracker_urls
        self.comment = comment
        self.created_by = created_by
        self.creation_date = creation_date
        self.base_location = location
        self.files = files
        self.name = name
        self.piece_length = piece_length
        self.pieces = pieces
        self.private = private
        self.info_hash = info_hash
        self.total_file_size = sum([f.size for f in self.files])

        if not pieces:
            self._collect_pieces()

        if not self.info_hash:
            self._compute_info_hash()

        self.trackers = [TrackerInfo(x, self.info_hash, self.total_file_size) for x in self.tracker_urls]

    def __str__(self):
        """
        Returns a pretty-printed string representing the torrent
        :return:    pretty-printed string
        """
        return "<Torrent object: {name} : {info_hash}>{".format(name=self.name, info_hash=self.info_hash)

    def _collect_pieces(self):
        """
        The real workhorse of torrent creation.
        Reads through all specified files, breaking them into piece_length chunks and storing their 20byte sha1
        digest into the pieces list
        :raises: CreationError
        """
        if not self.base_location:
            logger.error("Unable to create torrent. No base path specified. This is a programmer error.")
            raise CreationError

        base_path = self.base_location
        left_in_piece = 0
        next_pc = b""

        # how can I make this better? it'd be nice to have a generator that
        # abstracts away the file handling and just gives me the
        # sha1 digest of a self.piece_length chunk of the file
        for file_itm in self.files:
            with open(os.path.join(base_path, file_itm.path[0]), mode="rb") as f:
                current_pos = 0
                if left_in_piece > 0:
                    next_pc += f.read(left_in_piece)
                    self.pieces.append(hashlib.sha1(next_pc).digest().decode("ISO-8859-1"))
                    current_pos = left_in_piece
                    next_pc = b""
                    left_in_piece = 0

                while True:
                    if current_pos + self.piece_length <= file_itm.size:
                        self.pieces.append(hashlib.sha1(f.read(self.piece_length)).digest().decode("ISO-8859-1"))
                        current_pos += self.piece_length
                    else:
                        remainder_to_read = file_itm.size - current_pos
                        if remainder_to_read < 0:
                            break
                        next_pc += f.read(remainder_to_read)
                        left_in_piece = self.piece_length - remainder_to_read
                        break

    def _compute_info_hash(self):
        """
        Computes the 20-byte sha1 info hash digest of the contents of the info dictionary
        :raises: EncodeError
        """
        obj = self._to_obj()
        info_str = bencode(obj["info"])
        self.info_hash = hashlib.sha1(info_str.encode("ISO-8859-1")).digest()

    def _to_obj(self) -> OrderedDict:
        """
        converts a Torrent class instance to its equivalent python object for easier bencoding.
        :return: OrderedDict representing a torrent's metainfo
        :raises: CreationError
        """
        obj = OrderedDict()
        info = OrderedDict()
        files = []

        obj.setdefault("announce", self.tracker_urls[0])  # required key

        if len(self.tracker_urls) > 1:  # optional key
            obj.setdefault("announce-list", [self.tracker_urls[1:]])
        if self.comment:  # optional key
            obj.setdefault("comment", self.comment)
        if self.created_by:  # optional key
            obj.setdefault("created by", self.created_by)
        if self.creation_date:  # optional key
            obj.setdefault("creation date", self.creation_date)

        if len(self.files) > 1:
            for file_itm in self.files:
                f = OrderedDict()
                f.setdefault("length", file_itm.size)
                f.setdefault("path", file_itm.path)
                files.append(f)
            info.setdefault("files", files)
        else:
            info.setdefault("length", self.files[0].size)

        info.setdefault("name", self.name)  # required key
        info.setdefault("piece length", self.piece_length)  # required key
        info.setdefault("pieces", "".join(self.pieces))  # required key

        if self.private:  # optional key
            info.setdefault("private", 1)

        obj.setdefault("info", info)

        _validate_torrent_dict(obj)
        return obj

    @classmethod
    def _from_obj(cls, obj: OrderedDict, *, location: str = ""):
        """
        Creates a Torrent class from a metainfo dictionary created from a bencoded .torrent file
        :param obj:      bdecoded metainfo dictionary
        :param location: dirpath of torrent object (if we have one)
        :return:         Torrent instance
        :raises:         CreationError
        """
        _validate_torrent_dict(obj)

        files = []
        trackers = [obj["announce"]]
        pieces = list(_pc(obj["info"]["pieces"]))
        comment = obj.get("comment", "")
        created_by = obj.get("created by", "")
        creation_date = obj.get("creation date", 0)
        private = bool(obj["info"].get("private", False))
        info_dict = OrderedDict()
        info_dict.setdefault("info", obj["info"])
        info_str = bencode(obj["info"])
        info_hash = hashlib.sha1(info_str.encode("ISO-8859-1")).digest()

        if "announce-list" in obj:  # optional key
            trackers += obj["announce-list"][0]

        if "files" in obj["info"]:
            files += [FileItem(f["path"], f["length"]) for f in obj["info"]["files"]]
        else:
            files += FileItem(obj["info"]["name"], obj["info"]["length"])

        return cls(trackers, files, obj["info"]["name"], comment=comment, location=location,
                   created_by=created_by, creation_date=creation_date, pieces=pieces,
                   piece_length=obj["info"]["piece length"], private=private, info_hash=info_hash)

    @classmethod
    def from_file(cls, torrent_file: str):
        """
        Creates a torrent object from a torrent file
        :param torrent_file: path to .torrent file
        :return:             Torrent representing the .torrent file
        :raises:             CreationError
        """
        try:
            with open(torrent_file, mode='rb') as f:
                torrent_obj = bdecode(f.read())

            if torrent_obj is None:
                logger.error("Unable to create Torrent instance from empty file {file}.".format(file=torrent_file))
                raise CreationError

            logger.debug("Creating Torrent instance from file {file}".format(file=torrent_file))
            torrent = cls._from_obj(torrent_obj, location=os.path.dirname(torrent_file))
            logger.debug(
                "Created Torrent instance from {file} {torrent}".format(file=torrent_file, torrent=torrent.info_hash))
            return torrent
        except IOError as ioerr:
            logger.error("Unable to create Torrent instance. {file} does not exist.".format(file=torrent_file))
            raise CreationError from ioerr
        except (DecodeError, EncodeError) as e:
            logger.error("Unable to bdecode or bencode during creation {file}".format(file=torrent_file))
            raise CreationError from e

    @classmethod
    def from_path(cls, path: str, trackers: list, *, comment: str = "",
                  piece_size: int = 16384, private: bool = False):
        """
        Creates a Torrent from a given path, gathering piece hashes from given files.
        Supports creating torrents from single files and multiple files.
        :param path:       path from which to create the Torrent
        :param trackers:   tracker url
        :param comment:    optional,torrent's comment,defaults to ""
        :param piece_size: optional,piece size,defaults to default 16384
        :param private:    optional,private torrent?,defaults to False
        :return:           Torrent object
        :raises:           CreationError
        """
        files = []

        if not os.path.exists(path):
            logger.error("Path does not exist {path}".format(path=path))
            raise CreationError

        # gather files
        if os.path.isfile(path):
            base_path = os.path.dirname(path)
            name = os.path.basename(path)
            size = os.path.getsize(path)
            files.append(FileItem(name, size))
        elif os.path.isdir(path):
            base_path = path
            name = os.path.basename(path)

            # os.listdir returns paths in arbitrary order - possible danger here
            for f in os.listdir(path):
                size = os.path.getsize(os.path.join(path, f))
                fi = FileItem(f, size)
                fi.path = [fi.path]
                files.append(fi)
        else:
            logger.error("Error creating Torrent instance. Invalid file keys in metainfo dictionary.")
            raise CreationError

        logger.debug("Creating Torrent instance from path {path}".format(path=path))
        torrent = cls(trackers, files, name, location=base_path, comment=comment, private=private,
                      piece_length=piece_size)
        logger.debug("Created Torrent instance from path {path} {torrent}".format(path=path, torrent=torrent.info_hash))
        return torrent

    def to_file(self, save_path: str) -> None:
        """
        converts a Torrent instance to a dictionary representing the metainfo file,
        bencodes the dictionary to a bytestring and writes the file.
        :param save_path: path to save the torrent
        :raises:          CreationError
        """
        try:
            encoded_bytes = bencode(self._to_obj())
            with open(save_path, mode="wb") as f:
                logger.debug("Writing bencoded torrent metainfo dictionary file to {path}".format(path=save_path))
                f.write(encoded_bytes.encode("ISO-8859-1"))
        except (CreationError, EncodeError, IOError) as exc:
            logger.error("Unable to write torrent to file {path}.".format(path=save_path))
            raise CreationError from exc
        else:
            logger.debug("Wrote bencoded torrent metainfo dictionary file to {path}".format(path=save_path))
