#!/usr/bin/env python

"""
Testing decoding and encoding a torrent file.
"""
import os
import sys

import config
from torrent_utils.torrent import Torrent
from utils.exceptions import DecodeError, EncodeError, CreationError


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


def test_torrent_to_file(torrent_obj, path):
    assert isinstance(torrent_obj, Torrent), "[!!!] Invalid torrent object"

    print("[*] Writing torrent to {path}".format(path=path))
    try:
        torrent_obj.to_file(path)
    except EncodeError as ee:
        raise ee
    print("Success!")


if __name__ == '__main__':
    try:
        # Decode a torrent file into a Torrent object
        torrent_from_file = test_file_to_torrent(config.TEST_FILE)

        # Create a Torrent from a directory
        torrent_from_dir = test_dir_to_torrent(config.TEST_TORRENT_DIR)

        # Write the two torrents to respective .torrent files
        # these should be the same save the created by, creation date,
        # and comment
        test_torrent_to_file(torrent_from_file, config.TEST_OUTPUT_FILE)
        test_torrent_to_file(torrent_from_dir, config.TEST_TORRENT_DIR_OUTPUT)

    except (CreationError, DecodeError, EncodeError, ValueError, IOError) as e:
        print(e.message)
        sys.exit()
