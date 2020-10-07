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
import signal
import unittest

from opalescence import __version__
from opalescence.btlib.metainfo import MetaInfoFile
from ..btlib.client import ClientTorrent

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
            "handlers": ["stdout"],
            "propagate": False
        }
    },
    "root": {
        "level": "DEBUG",
        "handlers": ["stdout"]
    }
}


def main():
    """
    CLI entry point
    """
    argparser = create_argparser()

    try:
        args = argparser.parse_args()
        _LoggingConfig["root"]["level"] = args.loglevel
        logging.config.dictConfig(_LoggingConfig)
        logging.getLogger('asyncio').setLevel(logging.DEBUG)
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
                        version=__version__)
    parser.add_argument("-d", "--debug", help="Print debug-level output.",
                        action="store_const", dest="loglevel",
                        const=logging.DEBUG, default=logging.WARNING)
    parser.add_argument("-v", "--verbose", help="Print verbose output (but "
                                                "still less verbose than "
                                                "debug-level.)",
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
    logger = logging.getLogger("opalescence")
    logger.info(f"Running the test suite on the files in development.")

    loader = unittest.defaultTestLoader
    runner = unittest.TextTestRunner()
    suite = loader.discover(
        os.path.abspath(os.path.join(os.path.dirname(__file__), "tests")))
    runner.run(suite)


def download(file_path) -> None:
    """
    Downloads a .torrent file
    :param file_path: .torrent filepath argparse.Namespace object
    """
    asyncio.run(do_download(file_path.torrent_file, file_path.destination))


def d2(tfile, dest) -> None:
    asyncio.run(do_download(tfile, dest))


async def do_download(torrent_fp, dest_fp):
    logger = logging.getLogger("opalescence")
    logger.info(f"Downloading {torrent_fp} to {dest_fp}")

    loop = asyncio.get_event_loop()
    loop.set_debug(__debug__)
    torrent = ClientTorrent(MetaInfoFile.from_file(torrent_fp), dest_fp)
    start_task = loop.create_task(torrent.download())

    def signal_handler(_, __):
        logger.debug("SIGINT received.")
        start_task.cancel()  # raises the CancelledError below

    signal.signal(signal.SIGINT, signal_handler)

    try:
        # Main entry point
        await start_task
    except asyncio.CancelledError:
        logger.debug("CancelledError")
    except KeyboardInterrupt:
        logger.debug("Keyboard interrupt received.")
    except Exception as ex:
        logger.error(f"Unknown exception received: {type(ex).__name__}")
        logger.debug(ex, exc_info=True)
    finally:
        loop.close()
        logger.info(f"Shutting down. Thank you for using opalescence v{__version__}.")
        loop.stop()
