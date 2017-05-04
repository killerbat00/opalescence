# -*- coding: utf-8 -*-

"""
Library code for the bittorrent protocol.
"""
import logging

__all__ = ["bencode", "protocol", "torrent", "tracker", "client"]


def log_and_raise(msg: str, log: logging.Logger, exc: Exception, from_e: Exception = None) -> None:
    """
    Logs a message, then raises the specified exception, optionally from another exception.

    :param msg:    message to log on the module's logger
    :param log:    logger on which to log
    :param exc:    exception to raise
    :param from_e: exception from which to raise
    :raises exc:
    """
    if from_e:
        log.exception(msg)
        raise exc(msg) from from_e

    log.error(msg)
    raise exc(msg)
