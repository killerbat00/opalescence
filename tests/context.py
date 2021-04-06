# -*- coding: utf-8 -*-

"""
Provides a context for test files so the package's files will be resolved properly
"""

import os
import sys

# noinspection PyUnresolvedReferences
# noinspection PyUnresolvedReferences
from opalescence.btlib import client, protocol

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# TODO: This torrent may change as ubuntu releases a new . version of 16.04
# TODO: update handling here to use a dynamically generated torrent (maybe using an external lib for initial torrent generation?)
torrent_url = "https://releases.ubuntu.com/focal/ubuntu-20.04.1-live-server-amd64.iso.torrent"
