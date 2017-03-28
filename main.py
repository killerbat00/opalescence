# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testing decoding and encoding a torrent file.
"""

import logging
import logging.config
import os

from opalescence.args import init_argparsers
from opalescence.btlib.torrent import Torrent, CreationError


def test_path_to_torrent(path: str) -> Torrent:
    trackers = ["www.google.com", "www.google.com", "www.brianmorrow.net"]
    try:
        result = Torrent.from_path(path, trackers, comment="this is a comment! huzzah!")
    except CreationError as e:
        raise CreationError from e
    else:
        return result


def test_file_to_torrent(torrent_file: str) -> Torrent:
    try:
        result = Torrent.from_file(torrent_file)
    except CreationError as e:
        raise CreationError from e
    else:
        return result


def test_torrent_to_file(torrent_obj: Torrent, path: str):
    try:
        torrent_obj.to_file(path)
    except CreationError as e:
        raise CreationError from e


def main():
    """
    Main entry-point into Opalescence.
    """
    full_path = os.path.realpath(__file__)
    dirname = os.path.dirname(full_path)
    log_conf_path = os.path.join(dirname, "config", "logging.ini")
    logging.config.fileConfig(log_conf_path)

    logger = logging.getLogger("opalescence")
    logger.info("Initialized logging")

    argparser = init_argparsers()
    args = argparser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()

    # Deocde a torrent file used in qbittorrent with the hopes that
    # saving it again will allow me to open it in the same program
    # torrent_from_file = test_file_to_torrent(default.TEST_EXTERNAL_FILE)
    # test_torrent_to_file(torrent_from_file, default.TEST_EXTERNAL_OUTPUT)

    # Create a torrent from a directory and compare its info hash to one created
    # by qbittorrent for the same directory
    # my_torrent_from_dir = test_path_to_torrent(default.TEST_TORRENT_DIR)
    # q_torrent_from_dir = test_file_to_torrent(default.TEST_FILE)
    #test_torrent_to_file(my_torrent_from_dir, default.TEST_OUTPUT_FILE)

    ## first communication with the tracker
    # print((
    #    "[*] Making request to the tracker {tracker_url}".format(
    #        tracker_url=torrent_from_file.trackers[0].announce_url)))
    # if torrent_from_file.trackers[0].make_request():
    #    for peer in torrent_from_file.trackers[0].peer_list:
    #        try:
    #            peer.handshake()
    #        except:
    #            continue
    # else:
    #   print("Error")
