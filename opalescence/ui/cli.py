#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Command Line Interface for Opalescence (Clifo)
"""

import argparse
import asyncio
import functools
import logging
import logging.config
import logging.handlers
import os
import signal
import sys
import unittest
from queue import SimpleQueue as Queue

from opalescence import __version__
from opalescence.btlib.client import ClientTorrent
from opalescence.btlib.metainfo import MetaInfoFile


def main():
    """
    CLI entry point
    """
    parser = create_argparser()
    try:
        args = parser.parse_args()
        configure_logging(args.loglevel)
        args.func(args)
    except AttributeError:
        parser.print_help()


def create_argparser() -> argparse.ArgumentParser:
    """
    CLI argument parsing setup.
    :return:    argparse.ArgumentParser instance
    """
    parser = argparse.ArgumentParser()
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
    suite = loader.discover(os.path.abspath(os.path.join(os.path.dirname(__package__), "tests")))
    if suite:
        runner.run(suite)


def download(file_path) -> None:
    """
    Downloads a .torrent file
    :param file_path: .torrent filepath argparse.Namespace object
    """
    logger = logging.getLogger("opalescence")
    asyncio.run(do_download(file_path.torrent_file, file_path.destination))
    logger.info(f"Shutting down. Thank you for using opalescence v{__version__}.")


def d2(tfile, dest) -> None:
    asyncio.run(do_download(tfile, dest))


async def do_download(torrent_fp, dest_fp):
    logger = logging.getLogger("opalescence")
    logger.info(f"Downloading {torrent_fp} to {dest_fp}")

    loop = asyncio.get_event_loop()
    loop.set_debug(__debug__)
    torrent = ClientTorrent(MetaInfoFile.from_file(torrent_fp), dest_fp)
    start_task = torrent.download()

    def signal_received(s):
        logger.debug(f"{s} received. Shutting down...")
        start_task.cancel()

    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame), functools.partial(signal_received, signame))

    try:
        # Main entry point
        await start_task
    except asyncio.CancelledError:
        start_task.cancel()
        await asyncio.sleep(0)
    except Exception as ex:
        if not isinstance(ex, KeyboardInterrupt):
            logger.error(f"{type(ex).__name__} exception received.")
            logger.exception(ex, exc_info=True)


def configure_logging(log_level):
    stream_handler = logging.StreamHandler(stream=sys.stdout)
    formatter = logging.Formatter(fmt="[%(levelname)7s] %(asctime)s : %(name)40s : %(message)s")
    stream_handler.setFormatter(formatter)

    queue = Queue()
    queue_handler = LocalQueueHandler(queue)

    app_logger = logging.getLogger("opalescence")
    app_logger.setLevel(log_level)
    app_logger.addHandler(queue_handler)

    listener = logging.handlers.QueueListener(
        queue, *[stream_handler], respect_handler_level=True
    )
    listener.start()


class LocalQueueHandler(logging.handlers.QueueHandler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.enqueue(record)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.handleError(record)
