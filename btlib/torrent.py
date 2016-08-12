# -*- coding: utf-8 -*-

"""
Support for representing a .torrent file as a python class and creating a Torrent class (or .torrent file) from
a specified file or directory.

author: brian houston morrow
"""

import codecs
import hashlib
import ntpath
import os
import time
from collections import OrderedDict

import config
from .bencode import bdecode, bencode, DecodeError, EncodeError
from .tracker import TrackerInfo


def _pc(piece_string: bytes, length: int = 20, start: int = 0):
    """
    pieces a string into pieces of specified length.
    by default pieces into 20byte (160 bit) pieces
    typically used to piece the hashlist contained within the torrent info's pieces key
    :param piece_string:  string to piece
    :param length:
    :return: generator comprehension
    """
    return (piece_string[0 + i:length + i] for i in range(start, len(piece_string), length))


def _validate_torrent_dict(decoded_dict: dict) -> bool:
    """
    Verifies a given decoded dictionary contains valid keys to describe a torrent we can do something with.
    Currently only checks for the minimum required torrent keys for torrents describing files and directories.
    If a dictionary contains all valid keys + extra keys, it will be validated.
    :param decoded_dict:    dict representing bencoded .torrent file
    :return:                True if valid, else raises CreationError

    TODO: There's a subtle bug in here where you could have some keys that are required for single files and multiple
    files at the same time without having all of them defined for either. I think. Maybe. Probably.
    """
    min_req_keys = ["info", "announce"]
    min_info_req_keys = ["piece length", "pieces", "name"]
    min_single_req_keys = list(min_info_req_keys) + ["length"]
    min_mult_req_keys = list(min_info_req_keys) + ["files"]
    min_files_req_keys = ["length", "path"]

    dict_keys = list(decoded_dict.keys())

    if not dict_keys:
        raise CreationError("Unable to verify torrent dictionary. No valid keys in dictionary.")
    if len(dict_keys) != len(set(dict_keys)):
        raise CreationError("Unable to verify torrent dictionary. Duplicate keys in dictionary.")
    for key in min_req_keys:
        if key not in dict_keys:
            raise CreationError(
                "Unable to verify torrent dictionary. Required key not found: {required_key}".format(required_key=key))

    info_keys = list(decoded_dict["info"].keys())

    if not info_keys:
        raise CreationError("Unable to verify torrent info dictionary. No valid keys in info dictionary.")
    if len(info_keys) != len(set(info_keys)):
        raise CreationError("Unable to verify torrent info dictionary. Duplicate keys in dictionary.")
    for key in min_info_req_keys:
        if key not in info_keys:
            raise CreationError("Unable to verify torrent dictionary. \
            Required key not found in info dictionary: {required_key}".format(required_key=key))

        if len(decoded_dict["info"]["pieces"]) % 20 != 0:
            raise CreationError("Unable to verify torrent dictionary. Pieces string is not a multiple of 20")

    multiple_files = "files" in info_keys

    if multiple_files:
        file_list = decoded_dict["info"]["files"]

        if not file_list:
            raise CreationError("Unable to verify torrent dictionary. No file list.")
        for f in file_list:
            for key in list(f.keys()):
                if key not in min_files_req_keys:
                    raise CreationError("Unable to verify torrent dictionary. \
                    Required key not found in files dictionary for multiple files: {required_key}".format(
                        required_key=key))
        for key in min_mult_req_keys:
            if key not in info_keys:
                raise CreationError("Unable to verify torrent dictionary. \
                Required key not found in info dictionary for multiple files: {required_key}".format(required_key=key))
    else:
        for key in min_single_req_keys:
            if key not in info_keys:
                raise CreationError("Required key not found in info dictionary for single file: {required_key}".format(
                    required_key=key))
    # we made it!
    return True


class CreationError(Exception):
    """
    Raised when we encounter problems creating a torrent
    """
    pass


class FileItem(object):
    """
    An individual file within a torrent.
    """

    def __init__(self, path: str, size: int):
        """
        Initializes a new FileItem
        :param path:    file path
        :param size:    file size
        """
        self.path = path
        self.size = int(size)


class Torrent(object):
    """
    Relevant metadata for a torrent file
    """

    def __init__(self, tracker_urls, files, location, name, url_list,
                 comment="", created_by=config.FULL_NAME, creation_date=int(time.time()),
                 pieces=None, piece_length=16384, private=False, info_hash=""):
        """
        Initializes a torrent. Not typically used alone, instead, use Torrent.from_file or Torrent.from_path
        :param trackers:        list of tracker urls
        :param files:           list of files
        :param location:        output location
        :param name:            torrent's name
        :param url_list:        list of urls
        :param comment:         optional,comment
        :param created_by:      optional,defaults to opalescense
        :param creation_date:   optional,defaults to time of instantiation
        :param pieces:          optional,defaults to []
        :param piece_length:    optional,defaults to 16384 bytes; piece length in bytes
        :param private:         optional,defaults to False
        :param info_hash:       optional,defaults to ""
        """
        if pieces is None:
            pieces = []

        self.tracker_urls = tracker_urls
        self.comment = comment
        self.created_by = created_by
        self.creation_date = creation_date
        self.files = files
        self.save_location = location
        self.name = name
        self.piece_length = piece_length
        self.pieces = pieces
        self.private = private
        self.url_list = url_list
        self.info_hash = info_hash
        self.total_file_size = sum([f.size for f in self.files])
        self.trackers = [TrackerInfo(x, self.info_hash, self.total_file_size) for x in self.tracker_urls]

        if not pieces:
            self._collect_pieces()

        if not self.info_hash:
            self._compute_info_hash()

    def _collect_pieces(self):
        """
        The real workhorse of torrent creation.
        Reads through all specified files, breaking them into piece_length chunks and storing their 20byte sha1
        digest into the pieces list
        """
        base_path = config.TEST_TORRENT_DIR
        left_in_piece = 0
        next_pc = ""

        # how can I make this better? it'd be nice to have a generator that
        # abstracts away the file handling and just gives me the
        # sha1 digest of a self.piece_length chunk of the file
        for file_itm in self.files:
            with open(os.path.join(base_path, file_itm.path[0]), mode="rb") as f:
                current_pos = 0
                if left_in_piece > 0:
                    next_pc += f.read(left_in_piece)
                    self.pieces.append(hashlib.sha1(next_pc).digest())
                    current_pos = left_in_piece
                    next_pc = ""
                    left_in_piece = 0

                while True:
                    if current_pos + self.piece_length <= file_itm.size:
                        self.pieces.append(hashlib.sha1(f.read(self.piece_length)).digest())
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
        """
        info = OrderedDict()
        files = []

        if len(self.files) > 1:
            for file_itm in self.files:
                f = OrderedDict()
                f.setdefault(b"length", file_itm.size)
                f.setdefault(b"path", file_itm.path)
                files.append(f)
            info.setdefault(b"files", files)
        else:
            info.setdefault(b"length", self.files[0].size)

        info.setdefault(b"name", self.name)  # required key
        info.setdefault(b"piece length", self.piece_length)  # required key
        info.setdefault(b"pieces", "".join(self.pieces))  # required key

        if self.private:  # optional key
            info.setdefault(b"private", 1)

        self.info_hash = hashlib.sha1(bencode(info)).digest()

    # => Alternate constructors
    @staticmethod
    def from_file(torrent_file):
        # type (str) -> Torrent
        """
        Creates a torrent object from a torrent file
        :param torrent_file:    path to .torrent file
        :return:                Torrent representing the .torrent file
        """
        assert (os.path.exists(torrent_file))

        try:
            with codecs.open(torrent_file, mode='rb') as f:
                torrent_obj = bdecode(f.read())
        except DecodeError:
            raise

        if torrent_obj is not None:
            _validate_torrent_dict(torrent_obj)

            files = []
            trackers = [torrent_obj["announce"]]
            pieces = list(_pc(torrent_obj["info"]["pieces"]))
            url_list = []
            comment = ""
            created_by = ""
            creation_date = 0
            private = False
            info_dict = OrderedDict()
            info_str = bencode(torrent_obj["info"])
            info_hash = hashlib.sha1(info_str.encode("ISO-8859-1")).digest()
            info_dict.setdefault("info", torrent_obj["info"])

            if "announce-list" in torrent_obj:  # optional key
                trackers += torrent_obj["announce-list"][0]

            if "comment" in torrent_obj:  # optional key
                comment = torrent_obj["comment"]

            if "created by" in torrent_obj:  # optional key
                created_by = torrent_obj["created by"]

            if "creation date" in torrent_obj:  # optional key
                creation_date = torrent_obj["creation date"]

            if "files" in torrent_obj["info"]:
                for f in torrent_obj["info"]["files"]:
                    files.append(FileItem(f["path"], f["length"]))
            else:
                files.append(FileItem(torrent_obj["info"]["name"], torrent_obj["info"]["length"]))

            if "private" in torrent_obj["info"]:  # optional key
                private = bool(torrent_obj["info"]["private"])

            if "url-list" in torrent_obj:  # optional key
                url_list = torrent_obj["url-list"]

            return Torrent(trackers, files, torrent_file, torrent_obj["info"]["name"], url_list, comment=comment,
                           created_by=created_by, creation_date=creation_date, pieces=pieces,
                           piece_length=torrent_obj["info"]["piece length"], private=private, info_hash=info_hash)

    @staticmethod
    def from_path(path, trackers=None, comment="", piece_size=16384, private=False, url_list=None):
        """
        Creates a Torrent from a given path, gathering piece hashes from given files.
        Supports creating torrents from single files and multiple files.
        :param path:            path from which to create the Torrent
        :param trackers:        tracker url
        :param url_list:        list of urls
        :param private:         private torrent?
        :param comment:         torrent's comment
        :param piece_size:      piece size - default 16384
        :return:    Torrent object
        """
        files = []

        if not ntpath.exists(path):
            raise CreationError("Path does not exist {path}".format(path=path))

        # gather files
        if ntpath.isfile(path):
            name = ntpath.basename(path)
            size = ntpath.getsize(path)
            files.append(FileItem(name, size))
        elif ntpath.isdir(path):
            name = ntpath.basename(path)

            # os.listdir returns paths in arbitrary order - possible danger here
            for f in os.listdir(path):
                size = ntpath.getsize(ntpath.join(path, f))
                fi = FileItem(f, size)
                fi.path = [fi.path]
                files.append(fi)
        else:
            raise CreationError("Error creating torrent.")

        torrent = Torrent(trackers, files, config.TEST_TORRENT_DIR_OUTPUT, name,
                          url_list, comment=comment, private=private, piece_length=piece_size)
        return torrent

    # => Output
    def to_file(self, save_path):
        # type (Torrent, str) -> None
        """
        converts a Torrent class object to its equivalent python object for easier bencoding.
        :param save_path:   path to save the torrent
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

        if self.url_list:  # optional key
            obj.setdefault("url-list", self.url_list)

        try:
            _validate_torrent_dict(obj)
            encoded_bytes = bencode(obj)
            with open(save_path, mode="wb") as f:
                f.write(encoded_bytes.encode("ISO-8859-1"))
        except (CreationError, EncodeError):
            raise
