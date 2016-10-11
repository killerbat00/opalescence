# -*- coding: utf-8 -*-

"""
Provides support for application level argument parsing and creation

author: brian houston morrow
"""
import argparse
import logging
import os

from btlib.torrent import Torrent, CreationError

logger = logging.getLogger("opalescence." + __name__)


def init_argparsers() -> argparse.ArgumentParser:
    """
    Initializes the root argument parser and all relevant subparsers for supported commands.
    :return:    ArgumentParser
    """
    parser = argparse.ArgumentParser()
    logger.info("Initialized argument parser.")
    subparsers = parser.add_subparsers(title="Available commands",
                                       description="Opalescence currently supports the following commands.")
    # Creation
    add_create_parser(subparsers)

    # Other commands
    logger.info("Initialized argument subparsers.")
    return parser


def add_create_parser(subparser) -> None:
    """
    Creates the argument parser necessary for the creation command
    :param subparser:   subparser obtained from ArgumentParser().add_subparsers
    """
    create_parser = subparser.add_parser("create",
                                         help="create a .torrent file")
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
