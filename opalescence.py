# -*- coding: utf-8 -*-
# !/usr/bin/env python

"""
Testing decoding and encoding a torrent file.

author: brian houston morrow
"""
import asyncio
import signal
from concurrent.futures import CancelledError

import applib.args
import applib.logging
import default
from btlib.manager import Manager
from btlib.torrent import Torrent


def init_logging():
    """
    Configures the root logger for the application
    """
    logger = applib.logging.get_logger("opalescence")
    logger.info("Initialized logging.")
    return logger


def main():
    """
    Main entry-point into Opalescence.
    """
    logger = init_logging()
    argparser = applib.args.init_argparsers()
    args = argparser.parse_args()
    loop = asyncio.get_event_loop()

    t = Torrent(default.STAR_TREK)
    mgr = Manager(t)
    task = loop.create_task(mgr.start_download())

    def signal_handler(*_):
        logger.info("Exiting")

    signal.signal(signal.SIGINT, signal_handler)
    try:
        loop.run_until_complete(task)
    except CancelledError as ce:
        logger.debug("Event loop was cancelled")

if __name__ == '__main__':
    main()
