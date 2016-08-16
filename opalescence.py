# -*- coding: utf-8 -*-
# !/usr/bin/env python

"""
Testing decoding and encoding a torrent file.

author: brian houston morrow
"""
import argparse
import logging
import os
import sys

from btlib.torrent import Torrent, CreationError


def test_file_to_torrent(torrent_file):
    assert os.path.exists(torrent_file), "[!!!] Path does not exist %s" % torrent_file

    print(("[*] Creating torrent from {file}".format(file=torrent_file)))
    result = Torrent.from_file(torrent_file)
    print("Success!")
    return result


def test_torrent_to_file(torrent_obj, path):
    assert isinstance(torrent_obj, Torrent), "[!!!] Invalid torrent object"

    print(("[*] Writing torrent to {path}".format(path=path)))
    torrent_obj.to_file(path)
    print("Success!")


def _validate_trackers(trackers: list) -> list:
    """
    Used to validate  we have at least 1 valid tracker from the trackers specified when creating a torrent.
    To validate:
        - Invalidly formatted URls are ignored
        - Duplicate trackers are ignored
    If the list of valid trackers contains at least 1, returns a list of those trackers, [] otherwise
    :param trackers:    List of trackers provided in cli args
    :return:            List of valid trackers, [] if no valid trackers found
    """
    import validators.url
    import collections

    valid = []
    for x in trackers:
        if not validators.url(x):
            print("[?] Invalid url {url}".format(url=x))
            continue
        valid.append(x)

    dupes = [url for url, count in collections.Counter(valid).items() if count > 1]
    if len(dupes) > 1:
        pass

    return trackers


def create_torrent(create_args):
    """
    Creates a torrent from the arguments specified on the command line.
    :param create_args:     Namespace argument returned by the call to ArgumentParser.parse_args
    """
    src = create_args.source
    dest = create_args.destination
    err_prolog = "[!] Unable to create .torrent metainfo file."

    if not os.path.exists(src):
        print("{prolog} {path} does not exist".format(prolog=err_prolog, path=create_args.source))
        return

    trackers = _validate_trackers(create_args.trackers)
    if not trackers:
        print("{prolog} No valid trackers found.".format(prolog=err_prolog))
        return

    comment = create_args.comment
    private = create_args.private
    piece_size = create_args.piecesize

    try:
        print("[*] Creating .torrent metainfo file from {dir}\n" +
              "[**] Using trackers {trackers}".format(dir=create_args.source, trackers=trackers))

        torrent = Torrent.from_path(src, trackers=trackers, comment=comment, private=private, piece_size=piece_size)

        print("[*] Writing .torrent metainfo file to {dest}".format(dest=dest))

        torrent.to_file(dest)
    except CreationError as exc:
        print("{prolog} {dir}".format(prolog=err_prolog, dir=src))
        print("[!!] {info}".format(info=exc.__traceback__))
    else:
        print("[*] Success! {name} created from {source}, written to {dest}".format(name=torrent.name, source=create_args.source,
                                                                                    dest=create_args.destination))


def add_create_parser(subparser) -> None:
    """
    Creates the argument parser necessary for the creation command
    :param subparser:   subparser obtained from ArgumentParser().add_subparsers
    """
    create_parser = subparser.add_parser("create", help="create a .torrent file")
    create_parser.add_argument("-s", "--source", required=True, help="source file or directory")
    create_parser.add_argument("-d", "--destination", required=True, help=".torrent destination")
    create_parser.add_argument("-t", "--trackers", required=True, nargs="*",
                               help="space delimited list of URLs for this torrent's trackers. \
                               Invalid URLs and duplicate trackers will be ignored.\nAt least 1 tracker is required.")
    create_parser.add_argument("-c", "--comment", required=False, type=str, help="Torrent's comment", default="")
    create_parser.add_argument("-p", "--private", required=False, action="store_true", help="Private torrent")
    create_parser.add_argument("-pc", "--piecesize", required=False, type=int,
                               help="Torrent's piece size.", default=16384)
    create_parser.set_defaults(func=create_torrent)


def init_argparsers() -> argparse.ArgumentParser:
    """
    Initializes the root argument parser and all relevant subparsers for supported commands.
    :return:    ArgumentParser
    """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(title="Available commands",
                                       description="Opalescence currently supports the following commands.")
    # Creation
    add_create_parser(subparsers)

    # Other commands
    return parser


def init_logging():
    """
    Configures the root logger for the application
    :return:
    """
    sh = logging.StreamHandler(stream=sys.stdout)
    f = logging.Formatter(fmt="%(asctime)s: [%(levelname)s] %(message)s", datefmt="%m/%d/%Y %H:%M:%S", style="{")

    sh.setFormatter(f)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(sh)


def main():
    """
    Main entry-point into Opalescence.
    """
    init_logging()
    argparser = init_argparsers()
    args = argparser.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()



























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
