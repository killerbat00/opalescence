# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Opalescence is a simple torrent client.
"""
import argparse
import logging
import sys
from pathlib import Path

from opalescence import __version__
from opalescence.ui import cli, tui


def configure_logging(log_level):
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(fmt="[%(levelname)12s] %(asctime)s : %(name)s : %(message)s")
    stream_handler.setFormatter(formatter)

    app_logger = logging.getLogger("opalescence")
    app_logger.setLevel(log_level)
    app_logger.addHandler(stream_handler)


def create_argparser() -> argparse.ArgumentParser:
    """
    CLI argument parsing setup.
    :return:    argparse.ArgumentParser instance
    """
    parser = argparse.ArgumentParser(prog="python -m opalescence",
                                     description="A download-only bittorrent client.")
    parser.add_argument("--version", action="version",
                        version=__version__)
    parser.add_argument("-d", "--debug", help="Print debug-level output.",
                        action="store_const", dest="loglevel",
                        const=logging.DEBUG, default=logging.ERROR)
    parser.add_argument("-v", "--verbose", help="Print verbose output (but "
                                                "still less verbose than "
                                                "debug-level.)",
                        action="store_const", dest="loglevel",
                        const=logging.INFO)
    parser.add_argument("-t", "--tui", help="Use the terminal user interface (TUI).",
                        action="store_const", dest="ui_mode",
                        const="TUI", default="CLI")

    subparsers = parser.add_subparsers()
    download_parser = subparsers.add_parser("download",
                                            help="Download a .torrent file.")
    download_parser.add_argument('torrent_file',
                                 help="Path to the .torrent file to download.",
                                 type=Path)
    download_parser.add_argument('destination',
                                 help="File destination path.",
                                 type=Path)
    return parser


parser = create_argparser()
try:
    args = parser.parse_args()
    configure_logging(args.loglevel)
    if args.ui_mode == "CLI":
        cli.download(args)
    else:
        tui.download(args)
except AttributeError:
    parser.print_help()
