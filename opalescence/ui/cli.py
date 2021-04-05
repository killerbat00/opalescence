#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Command Line Interface for Opalescence
"""

import asyncio
import functools
import logging
import signal
from pathlib import Path

from opalescence import __version__
from opalescence.btlib.client import Client


def download(args) -> None:
    """
    Main entrypoint for the CLI.
    Downloads a .torrent file

    :param args: .torrent filepath argparse.Namespace object
    """
    logger = logging.getLogger("opalescence")
    torrent_fp: Path = args.torrent_file
    dest_fp: Path = args.destination
    try:
        if not torrent_fp.exists():
            logger.error(f"Torrent filepath does not exist.")
            raise SystemExit
        if not dest_fp.exists():
            logger.debug(f"Destination filepath does not exist. Creating {dest_fp}.")
            dest_fp.mkdir()
        if not dest_fp.is_dir():
            logger.error(f"Destination filepath is not a directory.")
            raise SystemExit

        asyncio.run(do_download(torrent_fp, dest_fp))
    finally:
        logger.info(f"Shutting down. Thank you for using opalescence v{__version__}.")


async def do_download(torrent_fp: Path, dest_fp: Path):
    assert torrent_fp.exists() and dest_fp.exists()

    logger = logging.getLogger("opalescence")
    logger.info(f"Downloading {torrent_fp} to {dest_fp}")

    loop = asyncio.get_event_loop()
    loop.set_debug(__debug__)
    client = Client()

    def signal_received(s):
        logger.debug(f"{s} received. Shutting down...")
        client.stop()

    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame), functools.partial(signal_received, signame))

    try:
        # Main entry point
        client.add_torrent(torrent_fp=torrent_fp, destination=dest_fp)
        await client.start_all()
    except Exception as ex:
        if not isinstance(ex, KeyboardInterrupt):
            logger.exception(f"{type(ex).__name__} exception received.", exc_info=True)
    finally:
        await client.stop_all()
