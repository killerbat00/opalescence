# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Testing decoding and encoding a torrent file.
"""

import argparse
import logging
import logging.config
import os

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


def create_logger():
    """
    Creates and configures the root logger
    :return: root logger
    """
    full_path = os.path.realpath(__file__)
    dirname = os.path.dirname(full_path)
    log_conf_path = os.path.join(dirname, "config", "logging.ini")
    logging.config.fileConfig(log_conf_path)
    logging.info("Initialized logging")


def main():
    """
    Main entry-point into Opalescence.
    """
    create_logger()
    logging.info("Initializing argument parser and subparsers")
    argparser = init_argparsers()

    try:
        args = argparser.parse_args()
        args.func(args)
    except AttributeError:
        logging.debug("Program invoked with no arguments")


def init_argparsers() -> argparse.ArgumentParser:
    """
    Initializes the root argument parser and all relevant subparsers for supported commands.
    :return:    ArgumentParser
    """
    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers()

    test_parser = subparsers.add_parser("test", help="Run the test suite")
    test_parser.set_defaults(func=run_tests)

    create_parser = subparsers.add_parser("create", help="create a .torrent file")
    create_parser.add_argument("-s", "--source",
                               required=True,
                               help="source file or directory")
    create_parser.add_argument("-d", "--destination",
                               required=True,
                               help=".torrent destination")
    create_parser.add_argument("-t", "--trackers",
                               required=True,
                               nargs="*",
                               help="space delimited list of URLs for this torrent's trackers. \
                               Invalid URLs and duplicate trackers will be ignored.\nAt least 1 tracker is required.")
    create_parser.add_argument("-c", "--comment",
                               required=False,
                               type=str,
                               help="Torrent's comment",
                               default="")
    create_parser.add_argument("-p", "--private",
                               required=False,
                               action="store_true",
                               help="Private torrent")
    create_parser.add_argument("-pc", "--piecesize",
                               required=False,
                               type=int,
                               help="Torrent's piece size.",
                               default=16384)
    create_parser.set_defaults(func=create_torrent)

    return parser


def create_torrent(create_args):
    """
    Creates a torrent from the arguments specified on the command line.
    :param create_args: Namespace argument returned by the call to ArgumentParser.parse_args
    """
    src = create_args.source
    dest = create_args.destination
    err_prolog = "[!] Unable to create .torrent metainfo file."

    if not os.path.exists(src):
        str = "{prolog} {path} does not exist".format(prolog=err_prolog, path=create_args.source)
        print(str)
        logger.info(str)
        return

    # trackers = _validate_trackers(create_args.trackers)
    trackers = create_args.trackers
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
        print("[*] Success! {name} created from {source}, written to {dest}".format(name=torrent.name,
                                                                                    source=create_args.source,
                                                                                    dest=create_args.destination))


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


def run_tests(args) -> None:
    logging.debug("Typically this would run the test suite. Currently, it does not.")


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
