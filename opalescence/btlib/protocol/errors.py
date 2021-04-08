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
