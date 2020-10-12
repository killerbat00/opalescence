# -*- coding: utf-8 -*-

__all__ = ['PeerError']


class PeerError(Exception):
    """
    Raised when we encounter an error communicating with the peer.
    """
