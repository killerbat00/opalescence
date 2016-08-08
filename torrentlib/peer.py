"""
Support for basic communication with a single peer - for now

TODO: connections to multiple peers
"""


class Peer(object):
    """
    Represents a peer and provides methods for communicating with said peer.
    """

    def __init__(self, ip, port):
        self.ip = ip
        self.port = port

    def __str__(self):
        return "{ip}:{port}".format(ip=self.ip, port=self.port)
