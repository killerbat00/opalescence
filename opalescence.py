# -*- coding: utf-8 -*-
# !/usr/bin/env python

"""
Testing decoding and encoding a torrent file.

author: brian houston morrow
"""
import asyncio

import applib.args
import applib.logging
import default
from btlib.manager import Manager
from btlib.torrent import Torrent, CreationError


def test_path_to_torrent(path: str) -> Torrent:
    try:
        result = Torrent.from_path(path, default.ANNOUNCE_LIST, comment="this is a comment! huzzah!")
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


def init_logging():
    """
    Configures the root logger for the application
    """
    logger = applib.logging.get_logger("opalescence")
    logger.info("Initialized logging.")


def main():
    """
    Main entry-point into Opalescence.
    """
    init_logging()
    argparser = applib.args.init_argparsers()
    args = argparser.parse_args()
    if args and hasattr(args, 'func'):
        args.func(args)
    else:
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(doit())
        loop.run_forever()


async def doit():
    # my_torrent_from_dir = test_path_to_torrent(default.TEST_TORRENT_DIR)
    # q_torrent_from_dir = test_file_to_torrent(default.TEST_EXTERNAL_FILE)
    # assert (my_torrent_from_dir == q_torrent_from_dir)

    # star_trek = test_file_to_torrent(default.STAR_TREK)
    mgr = Manager([default.STAR_TREK])
    return mgr.start_download()


if __name__ == '__main__':
    main()
