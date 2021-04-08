# -*- coding: utf-8 -*-

"""
All application defined and thrown BitTorrent protocol-related errors.
"""


class DecodeError(Exception):
    """
    Raised when there's an issue decoding a bencoded object.
    """


class EncodeError(Exception):
    """
    Raised when there's an issue bencoding an object.
    """
