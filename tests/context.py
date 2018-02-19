# -*- coding: utf-8 -*-

"""
Provides a context for test files so the package's files will be resolved properly
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# noinspection PyUnresolvedReferences
from opalescence.btlib import bencode
# noinspection PyUnresolvedReferences
from opalescence.btlib import metainfo
# noinspection PyUnresolvedReferences
from opalescence.btlib import tracker
# noinspection PyUnresolvedReferences
from opalescence.btlib import protocol
# noinspection PyUnresolvedReferences
from opalescence.btlib import client

#TODO: This torrent may change as ubuntu releases a new . version of 16.04
#TODO: update handling here to use a dynamically generated torrent (maybe using an external lib for initial torrent generation?)
torrent_url = "http://releases.ubuntu.com/16.04/ubuntu-16.04.3-desktop-amd64.iso.torrent"
