import hashlib
import ntpath
import os
import time
from collections import OrderedDict

import config
import utils.decorators
from bencoding import bdecode
from utils.exceptions import CreationError, DecodeError


@utils.decorators.log_this
def _pc(piece_string, length=20):
    # type (str, int) -> generator comprehension
    """
    pieces a string into pieces of specified length.
    by default pieces into 20byte (160 bit) pieces
    typically used to piece the hashlist contained within the torrent info's pieces key
    :param piece_string:  string to piece
    :param length:
    :return: generator comprehension
    """
    return (piece_string[0+i:length+i] for i in range(0, len(piece_string), length))


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
                 comment="", created_by=config.FULL_NAME, creation_date=int(time.time()),
                 pieces=None, piece_length=16384, private=False):
        """
        Initializes a torrent. Not typically used alone, instead, use Torrent.from_file or Torrent.from_path
        :param announce:        announce url
        :param announce_list:   announce urls
        :param files:           list of files
        :param location:        output location
        :param name:            torrent's name
        :param url_list:        list of urls
        :param comment:         optional, comment
        :param created_by:      optional, defaults to opalescense
        :param creation_date:   optional, defaults to time of instantiation
        :param pieces:          optional, defaults to []
        :param piece_length:    optional, defaults to 16384
        :param private:         optional, defaults to False
        """
        if pieces is None:
            pieces = []

        self.announce = announce
        self.announce_list = announce_list
        self.comment = comment
        self.created_by = created_by
        self.creation_date = creation_date
        self.files = files
        self.location = location
        self.name = name
        self.piece_length = piece_length
        self.pieces = pieces
        self.private = private
        self.url_list = url_list
        self.block_size = piece_length

        if pieces is []:
            self._collect_pieces()

    @utils.decorators.log_this
    def _collect_pieces(self):
        """
        The real workhourse of torrent creation.
        Reads through all specified files, breaking them into piece_length chunks and storing their 160bit sha1
        digest into the pieces list
        """
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

    @staticmethod
    @utils.decorators.log_this
    def from_file(torrent_file):
        # type (str) -> Torrent
        """
        Creates a torrent object from a torrent file
        :param torrent_file:    path to .torrent file
        :return:                Torrent representing the .torrent file
        """
        assert(os.path.exists(torrent_file))

        try:
            with open(torrent_file, mode='rb') as f:
                torrent_obj = bdecode(f.read())
                print(torrent_obj)
        except DecodeError() as e:
            raise e

        if torrent_obj is not None:
            files = []
            pieces = list(_pc(torrent_obj["info"]["pieces"]))
            announce_list = None

            if "announce-list" in torrent_obj:
                announce_list = torrent_obj["announce-list"]

            if "files" in torrent_obj["info"]:
                for f in torrent_obj["info"]["files"]:
                    files.append(FileItem(f["path"], f["length"]))
            else:
                files.append(FileItem(torrent_obj["info"]["name"], torrent_obj["info"]["length"]))

            torrent = Torrent(torrent_obj["announce"], announce_list, files, torrent_file,
                              torrent_obj["info"]["name"], torrent_obj["url-list"], comment=torrent_obj["comment"],
                              created_by=torrent_obj["created by"], creation_date=torrent_obj["creation date"],
                              pieces=pieces, piece_length=torrent_obj["info"]["piece length"],
                              private=bool(torrent_obj["info"]["private"]))

            return torrent

    @staticmethod
    @utils.decorators.log_this
    def from_path(path, announce=None, announce_list=None, comment="", piece_size=16384, private=False, url_list=None):
        """
        Creates a Torrent from a given path, gathering piece hashes from given files.
        Supports creating torrents from single files and multiple files.
        :param path:            path from which to create the Torrent
        :param announce:        tracker url
        :param announce_list:   list of tracker urls
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
            files.append(FileItem(name, size, 0))
        elif ntpath.isdir(path):
            name = ntpath.basename(path)

            for f in os.listdir(path):
                size = ntpath.getsize(ntpath.join(path, f))
                files.append(FileItem(f, size))
        else:
            raise CreationError("Error creating torrent.")

        torrent = Torrent(announce, announce_list, files, config.TEST_TORRENT_DIR_OUTPUT, name,
                          url_list, comment=comment, private=private, piece_length=piece_size)
        return torrent

    @utils.decorators.log_this
    def to_file(self, save_path):
        # type (Torrent) -> OrderedDict
        """
        converts a Torrent class object to its equivalent python object for easier bencoding.
        :param self:        instance of Torrent
        :param save_path:   path to save the torrent
        """
        assert(os.path.exists(save_path))

        obj = OrderedDict()
        info = OrderedDict()
        files = []

        obj.setdefault("announce", self.announce)
        if self.announce_list is not None:
            obj.setdefault("announce-list", [self.announce_list])

        obj.setdefault("created by", self.created_by)
        obj.setdefault("creation date", self.creation_date)
        if self.comment != "":
            obj.setdefault("comment", self.comment)
        obj["created by"] = self.created_by
        obj["creation date"] = self.creation_date

        for file_itm in self.files:
            f = OrderedDict()
            f['length'] = file_itm.size
            f['path'] = [file_itm.path]
            files.append(f)

