# -*- coding: utf-8 -*-
# !/usr/bin/env python

"""
Testing decoding and encoding a torrent file.

author: brian houston morrow
"""
import argparse
import os

import config
from btlib.torrent import Torrent


def test_file_to_torrent(torrent_file):
    assert os.path.exists(torrent_file), "[!!!] Path does not exist %s" % torrent_file

    print(("[*] Creating torrent from {file}".format(file=torrent_file)))
    result = Torrent.from_file(torrent_file)
    print("Success!")
    return result


def test_dir_to_torrent(directory):
    assert os.path.exists(directory), "[!!!] Path does not exist %s" % directory

    print(("[*] Creating torrent from {dir}".format(dir=directory)))
    result = Torrent.from_path(directory, trackers=[config.ANNOUNCE] + config.ANNOUNCE_LIST,
                               url_list=config.URL_LIST, private=config.PRIVATE,
                               comment="This is a super awesome comment!")
    print("Success!")
    return result


def test_torrent_to_file(torrent_obj, path):
    assert isinstance(torrent_obj, Torrent), "[!!!] Invalid torrent object"

    print(("[*] Writing torrent to {path}".format(path=path)))
    torrent_obj.to_file(path)
    print("Success!")


def create_torrent(args):
    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title="Available commands",
                                       description="Opalescence currently supports the following commands.")
    create_parser = subparsers.add_parser("create", help="create a .torrent file", aliases=['c'])
    create_parser.add_argument("-s", "--source", required=True, nargs=1, help="source file or directory")
    create_parser.add_argument("-d", "--destination", required=True, nargs=1, help=".torrent destination")
    create_parser.set_defaults(func=create_torrent)
    args = parser.parse_args()
    args.func(args)
    print("A!")






























    # Decode a torrent file into a Torrent object
    # torrent_from_file = test_file_to_torrent(config.TEST_FILE)

    # Deocde a torrent file used in qbittorrent with the hopes that
    # saving it again will allow me to open it in the same program
    # it works!
#    torrent_from_file = test_file_to_torrent(config.TEST_EXTERNAL_FILE)
#    test_torrent_to_file(torrent_from_file, config.TEST_EXTERNAL_OUTPUT)
#
#    # first communication with the tracker
#    print((
#        "[*] Making request to the tracker {tracker_url}".format(
#            tracker_url=torrent_from_file.trackers[0].announce_url)))
#    if torrent_from_file.trackers[0].make_request():
#        print("Success!")
#        for peer in torrent_from_file.trackers[0].peer_list:
#            try:
#                peer.handshake()
#            except socketerror:
#                continue
#        torrent_from_file.trackers[0].peer_list[0].handshake()
#    else:
#        print("Error")

        # Create a Torrent from a directory
        # torrent_from_dir = test_dir_to_torrent(config.TEST_TORRENT_DIR)

        # Write the two torrents to respective .torrent files
        # these should be the same save the created by, creation date,
        # and comment
        # test_torrent_to_file(torrent_from_file, config.TEST_OUTPUT_FILE)
        # test_torrent_to_file(torrent_from_dir, config.TEST_TORRENT_DIR_OUTPUT)
