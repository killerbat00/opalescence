#!/usr/bin/env python

"""
Testing decoding and encoding a torrent file.
"""
import os
import sys

import config
from torrent_utils.torrent import Torrent
import torrent_utils.bencoding as bencoding
from torrent_utils.bencoding import bencode, bdecode
from utils.exceptions import DecodeError, EncodeError, CreationError


def test_decode_file(f):
    assert os.path.exists(f), "[!!!] File does not exist %s" % f
    print("[*] Decoding file {tfile}".format(tfile=f))
    with open(f, mode='rb') as tfile:
        trepr = bdecode(tfile.read())
    print("{obj}".format(obj=trepr))
    return trepr


def test_encode_obj(obj):
    print("[*] Encoding object {obj}".format(obj=obj))
    tstr = bencode(obj)
    print("{result}".format(result=tstr))
    return tstr


def test_obj_to_file(obj, outfile):
    print("[*] Writing file {f}".format(f=outfile))
    with open(outfile, mode='wb') as tfile:
        tfile.write(bencode(obj))
    print("Success!")


def test_file_to_torrent(torrent_file):
    assert os.path.exists(torrent_file), "[!!!] Path does not exist %s" % torrent_file
    print("[*] Creating torrent from {file}".format(file=torrent_file))
    result = Torrent.from_file(torrent_file)
    print("Success!")
    return result


def test_dir_to_torrent(directory):
    assert os.path.exists(directory), "[!!!] Path does not exist %s" % directory
    print("[*] Creating torrent from {dir}".format(dir=directory))
    result = Torrent.from_path(directory, announce=config.ANNOUNCE, announce_list=config.ANNOUNCE_LIST,
                               url_list=config.URL_LIST, private=config.PRIVATE,
                               comment="This is a super awesome comment!")
    print("Success!")
    return result


def test_pp_bencoding(bencoded_str):
    print("[*] Pretty printing {str}".format(str=bencoded_str))
    bencoding.pretty_print(bencoded_str)
    print("Success!")


if __name__ == '__main__':
    try:

        # Decode a torrent file into a Torrent object
        torrent_from_file = test_file_to_torrent(config.TEST_FILE)

        # Create a Torrent from a directory
        torrent_from_dir = test_dir_to_torrent(config.TEST_TORRENT_DIR)

#        # Write the newly created torrent to a file
#        torrent_from_dir.write_file(path)
#
#
#        # Decode a file into a python object
#        torrent_repr = test_decode_file(config.TEST_FILE)
#
#        # Encode a python object
#        torrent_str = test_encode_obj(torrent_repr)
#
#        # Write a python object to a torrent file
#        test_obj_to_file(torrent_repr, config.TEST_OUTPUT_FILE)
#
#        # Create a Torrent from a directory
#        test_torrent = test_dir_to_torrent(config.TEST_TORRENT_DIR)
#
#        # Pretty print a bencoded string
#        test_pp_bencoding(torrent_repr)
        print("halt")

    except (CreationError, DecodeError, EncodeError, ValueError, IOError) as e:
        print(e.message)
        sys.exit()
