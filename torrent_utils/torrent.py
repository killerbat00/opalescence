import config
import ntpath
import os
import time
import hashlib

import utils.decorators

from collections import OrderedDict
from utils.exceptions import CreationError
from bencoding import bencode, bdecode


class FileItem(object):
    """
    An individual file within a torrent.
    """
    @utils.decorators.log_this
    def __init__(self, path, size):
        # type (str, int, int) -> FileItem
        """
        Initializes a new FileItem
        :param path:    file path
        :param size:    file size
        """
        self.path = path
        self.size = size


class Torrent(object):
    """
    Relevant metadata for a torrent file
    """
    @utils.decorators.log_this
    def __init__(self, announce, announce_list, files, location, name, url_list,
                 comment="", piece_length=16384, private=False):
        self.announce = announce
        self.announce_list = announce_list
        self.comment = comment
        self.created_by = config.FULL_NAME
        self.creation_date = int(time.time())
        self.files = files
        self.location = location
        self.name = name
        self.piece_length = piece_length
        self.pieces = []
        self.private = private
        self.url_list = url_list
        self.block_size = piece_length

    def _collect_pieces(self):
        base_path = config.TEST_TORRENT_DIR
        left_in_piece = 0
        next_pc = ""

        # how can I make this better? it'd be nice to have a generator that
        # abstracts away the file handling and just gives me the
        # sha1 digest of a self.piece_length chunk of the file
        for file_itm in self.files:
            with open(os.path.join(base_path, file_itm.path), mode="rb") as f:
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

    @utils.decorators.log_this
    def _to_pyobj(self):
        # type (Torrent) -> OrderedDict
        """
        converts a Torrent class object to its equivalent python object for easier bencoding.
        :param self: instance of Torrent
        :return:    OrderedDict of torrent information
                    None on error
        """
        obj = OrderedDict()
        info = OrderedDict()
        files = []

        obj["created by"] = self.created_by
        obj["creation date"] = self.creation_date

        for file_itm in self.files:
            f = OrderedDict()
            f['length'] = file_itm.size
            f['path'] = [file_itm.path]
            files.append(f)

    @staticmethod
    @utils.decorators.log_this
    def from_file(torrent_file):
        # type (str) -> Torrent
        """
        Creates a torrent object from a torrent file
        :param torrent_file:    path to .torrent file
        :return:                Torrent representing the .torrent file
        """
        # TODO: add proper error handling
        assert(os.path.exists(torrent_file))

        mult_files = False
        min_required_keys = ["announce", "info"]
        min_required_keys = {"announce", "info"}
        info_required_keys = {"name", "piece length", "pieces"}
        single_required_keys = list(min_required_keys).append("length")
        mult_required_keys = list(min_required_keys).append("files")
        file_dict_required_keys = ["path", "length"]

        with open(torrent_file, mode='rb') as f:
            torrent_obj = bdecode(f.read())

        # TODO: there should be some validation surrounding expected keys in the torrent_obj to validate the torrent
        # min required keys: announce, info, name, piece length, pieces
        # required for single file: min required keys + length
        # required for mult files: min required keys + files
        # required in mult files: path, length
        # always optional: comment, url-list
        if torrent_obj is not None:
            for k in min_required_keys:
                if k not in torrent_obj:
                    raise CreationError("Cannot create from file. Invalid key")

            torrent = Torrent(torrent_obj["announce"], [], [], torrent_file,
                              torrent_obj["info"]["name"], torrent_obj["url-list"],
                              piece_length=torrent_obj["info"]["piece length"], comment=torrent_obj["comment"],
                              private=bool(torrent_obj["info"]["private"]))
            if "announce-list" in torrent_obj:
                torrent.announce_list = torrent_obj["announce-list"]

            torrent.created_by = torrent_obj["created by"]
            torrent.creation_date = torrent_obj["creation date"]

            if "files" in torrent_obj["info"]:
                for f in torrent_obj["info"]["files"]:
                    torrent.files.append(FileItem(f["path"], f["length"]))
            else:
                torrent.files.append(FileItem(torrent.name, torrent_obj["info"]["length"]))

            # pieces
            piece_str = bytearray()
            piece_str.extend(torrent_obj["info"]["pieces"])
            torrent_obj.pieces = list(torrent._pc(torrent_obj["info"]["pieces"], 160))

            return torrent

    def _pc(self, string, length):
        # TODO: iterate 160 bits over a time.
        return (string[0+i:length+i] for i in range(0, len(string), length))

    @staticmethod
    @utils.decorators.log_this
    def from_path(path, announce=None, announce_list=None, url_list=None, private=False, comment=""):
        files = []

        if not ntpath.exists(path):
            raise CreationError("Path does not exist {path}".format(path=path))

        # gather files
        if ntpath.isfile(path):
            name = ntpath.basename(path)
            size = ntpath.getsize(path)
            files.append(FileItem(name, size, 0))
        elif ntpath.isdir(path):
            name = ntpath.basename(path)

            for f in os.listdir(path):
                size = ntpath.getsize(ntpath.join(path, f))
                files.append(FileItem(f, size))
        else:
            raise CreationError("Error creating torrent.")

        torrent = Torrent(announce, announce_list, files, config.TEST_TORRENT_DIR_OUTPUT, name,
                          url_list, comment=comment, private=private)

        torrent._collect_pieces()
        return torrent
