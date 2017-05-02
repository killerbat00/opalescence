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
from opalescence.btlib import torrent
# noinspection PyUnresolvedReferences
from opalescence.btlib import tracker
# noinspection PyUnresolvedReferences
from opalescence.btlib import protocol
# noinspection PyUnresolvedReferences
from opalescence.btlib import client
