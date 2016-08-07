#!/usr/bin/env python

"""
Testing decoding and encoding a torrent file.

author: brian houston morrow
"""
import os

import config
from torrentlib.comm import TrackerHttpRequest, TrackerResponseError
from torrentlib.torrent import Torrent


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
    torrent_obj.to_file(path)
    print("Success!")


if __name__ == '__main__':
    # Decode a torrent file into a Torrent object
    # torrent_from_file = test_file_to_torrent(config.TEST_FILE)

    # Deocde a torrent file used in qbittorrent with the hopes that
    # saving it again will allow me to open it in the same program
    # it works!
    torrent_from_file = test_file_to_torrent(config.TEST_EXTERNAL_FILE)
    # test_torrent_to_file(torrent_from_file, config.TEST_EXTERNAL_OUTPUT)

    try:
        tracker_request = TrackerHttpRequest(torrent_from_file)
        tracker_resp = tracker_request.make_request()
    except TrackerResponseError as tre:
        raise tre

    # Create a Torrent from a directory
    # torrent_from_dir = test_dir_to_torrent(config.TEST_TORRENT_DIR)

    # Write the two torrents to respective .torrent files
    # these should be the same save the created by, creation date,
    # and comment
    # test_torrent_to_file(torrent_from_file, config.TEST_OUTPUT_FILE)
    # test_torrent_to_file(torrent_from_dir, config.TEST_TORRENT_DIR_OUTPUT)
