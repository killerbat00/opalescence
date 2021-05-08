# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Opalescence is a simple torrent client.
"""
import argparse
import logging
import sys
from pathlib import Path

from opalescence import __version__, __author__, __year__, get_app_config
from opalescence.ui import cli, tui


def configure_logging(log_level, app_config):
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)12s]: %(name)s : %(message)s")
    # file_handler = logging.FileHandler(os.path.expanduser("~") + "/opl.log")
    # file_handler.setFormatter(formatter)
    app_logger = logging.getLogger("opalescence")
    app_logger.setLevel(log_level)
    # app_logger.addHandler(file_handler)

    if True:  # not app_config.use_cli:
        stream_handler = logging.StreamHandler(stream=sys.stdout)
        stream_handler.setFormatter(formatter)
        app_logger.addHandler(stream_handler)


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
                    const="TUI", default="TUI")

subparsers = parser.add_subparsers()
download_parser = subparsers.add_parser("download",
                                        help="Download a .torrent file.")
download_parser.add_argument('torrent_file',
                             help="Path to the .torrent file to download.",
                             type=Path)
download_parser.add_argument('destination',
                             help="File destination path.",
                             type=Path)

try:
    args = parser.parse_args()
    config = get_app_config()
    if args.ui_mode == "CLI":
        print(f"Welcome to opalescence v{__version__}.")
        config.use_cli = True
        configure_logging(args.loglevel, config)
        cli.download(args)
    else:
        config.use_cli = False
        configure_logging(args.loglevel, config)
        tui.start(args)
except AttributeError:
    parser.print_help()
finally:
    print(f"Thank you for using opalescence v{__version__}.")
    print(f"Opalescence was created by: {__author__} (c) {__year__}")
