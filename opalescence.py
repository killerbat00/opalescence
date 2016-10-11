# -*- coding: utf-8 -*-
# !/usr/bin/env python

"""
Testing decoding and encoding a torrent file.

author: brian houston morrow
"""
import applib.args
import applib.logging
import default
from btlib.torrent import Torrent, CreationError


def test_path_to_torrent(path: str) -> Torrent:
    try:
        result = Torrent.from_path(path, default.ANNOUNCE_LIST, comment="this is a comment! huzzah!")
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


def init_logging():
    """
    Configures the root logger for the application
    """
    logger = applib.logging.get_logger("opalescence")
    logger.info("Initialized logging.")


def main():
    """
    Main entry-point into Opalescence.
    """
    init_logging()


#    argparser = applib.args.init_argparsers()
#    args = argparser.parse_args()
#    args.func(args)


if __name__ == '__main__':
    main()

    # Deocde a torrent file used in qbittorrent with the hopes that
    # saving it again will alloASw me to open it in the same program
    torrent_from_file = test_file_to_torrent(default.TEST_EXTERNAL_FILE)
    test_torrent_to_file(torrent_from_file, default.TEST_EXTERNAL_OUTPUT)

    # Create a torrent from a directory and compare its info hash to one created
    # by qbittorrent for the same directory
    my_torrent_from_dir = test_path_to_torrent(default.TEST_TORRENT_DIR)
    q_torrent_from_dir = test_file_to_torrent(default.TEST_EXTERNAL_FILE)
    test_torrent_to_file(my_torrent_from_dir, default.TEST_EXTERNAL_OUTPUT)
    assert (my_torrent_from_dir == q_torrent_from_dir)

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
