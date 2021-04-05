# -*- coding: utf-8 -*-

"""
Command Line Interface for Opalescence
"""

import asyncio
import functools
import logging
import signal
from pathlib import Path

from opalescence.btlib import Client

logger = logging.getLogger("opalescence")


def download(args) -> None:
    """
    Main entrypoint for the CLI.
    Downloads a .torrent file

    :param args: .torrent filepath argparse.Namespace object
    """
    torrent_fp: Path = args.torrent_file
    dest_fp: Path = args.destination

    if not torrent_fp.exists():
        logger.error(f"Torrent filepath does not exist.")
        raise SystemExit
    if not dest_fp.exists():
        logger.debug(f"Destination filepath does not exist. Creating {dest_fp}.")
        dest_fp.mkdir()
    if not dest_fp.is_dir():
        logger.error(f"Destination filepath is not a directory.")
        raise SystemExit

    asyncio.run(_download(torrent_fp, dest_fp))


async def _download(torrent_fp, dest_fp):
    logger.info(f"Downloading {torrent_fp} to {dest_fp}")

    loop = asyncio.get_event_loop()
    loop.set_debug(__debug__)
    client = Client()

    def signal_received(s):
        logger.debug(f"{s} received. Shutting down...")
        client.stop()

    for signame in ('SIGINT', 'SIGTERM'):
        loop.add_signal_handler(getattr(signal, signame), functools.partial(signal_received, signame))

    client.add_torrent(torrent_fp=torrent_fp, destination=dest_fp)
    await client.start_all()
    await client.stop_all()
