# -*- coding: utf-8 -*-

"""
All application defined BitTorrent protocol-related errors.
"""


class DecodeError(Exception):
    """
    Raised when there's an issue decoding a bencoded object.
    """


class EncodeError(Exception):
    """
    Raised when there's an issue bencoding an object.
    """


class MetaInfoCreationError(Exception):
    """
    Raised when we encounter problems creating a torrent.
    """


class TrackerConnectionError(Exception):
    """
    Raised when there's an error with the TrackerConnection.
    """


class NoTrackersError(Exception):
    """
    Raised when there are no trackers to accept an announce.
    """


class TrackerConnectionCancelledError(Exception):
    """
    Raised when the connection has been cancelled by the application.
    """


class NonSequentialBlockError(Exception):
    """
    Raised when the peer sends a non-sequential block.
    """
