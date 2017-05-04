#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Command Line Interface for Opalescence (Clifo)
"""

import argparse
import asyncio
import logging
import logging.config
import os
import unittest

import opalescence
from ..btlib.client import Client
from ..btlib.torrent import MetaInfoFile

_LoggingConfig = {
    "version": 1,
    "formatters": {
        "basic": {
            "format": "%(asctime)s : %(name)s : [%(levelname)s] %(message)s"
        }
    },
    "handlers": {
        "stdout": {
            "class": "logging.StreamHandler",
            "level": "DEBUG",
            "formatter": "basic",
            "stream": "ext://sys.stdout"

        }
    },
    "loggers": {
        "opalescence": {
            "level": "DEBUG",
            "handlers": ["stdout"]
        }
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["stdout"]
    }
}

logger = None


def main():
    """
    CLI entry point
    """
    global logger
    argparser = create_argparser()

    try:
        args = argparser.parse_args()
        _LoggingConfig["root"]["level"] = args.loglevel
        logging.config.dictConfig(_LoggingConfig)
        logger = logging.getLogger("opalescence")
        args.func(args)
    except AttributeError:
        argparser.print_help()


def create_argparser() -> argparse.ArgumentParser:
    """
    Initializes the root argument parser and any necessary
    subparsers for supported subcommands.
    :return:    argparse.ArgumentParser instance
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", action="version",
                        version=opalescence.__version__)
    parser.add_argument("-d", "--debug", help="Print debug-level output.",
                        action="store_const", dest="loglevel",
                        const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument("-v", "--verbose", help="Print verbose output (but "
                                                "still less verbose than "
                                                "debug-level.",
                        action="store_const", dest="loglevel",
                        const=logging.INFO)

    subparsers = parser.add_subparsers()
    test_parser = subparsers.add_parser("test", help="Run the test suite")
    test_parser.set_defaults(func=test)
    download_parser = subparsers.add_parser("download",
                                            help="Download a .torrent file.")
    download_parser.add_argument('torrent_file',
                                 help="Path to the .torrent file to download.")
    download_parser.add_argument('destination',
                                 help="File destination path.")
    download_parser.set_defaults(func=download)
    return parser


def test(_) -> None:
    """
    Runs the test suite found in the tests/ directory
    :param _: unused
    """
    logging.info(f"Running the test suite on the files in development.")

    loader = unittest.defaultTestLoader()
    runner = unittest.TextTestRunner()
    suite = loader.discover(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "tests")))
    runner.run(suite)


def download(file_path) -> None:
    """
    Downloads a .torrent file
    :param file_path: .torrent filepath argparse.Namespace object
    """
    logging.info(f"Downloading {file_path.torrent_file} to "
                 f"{file_path.destination}")

    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    torrent = MetaInfoFile.from_file(file_path.torrent_file)
    client = Client()
    client.download(torrent)

    try:
        loop.run_forever()
    except asyncio.CancelledError:
        logging.warning("Event loop was cancelled")
    except KeyboardInterrupt:
        logger.warning("Keyboard Interrupt received.")
    finally:
        loop.close()
