# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Opalescence is a simple torrent client written using Python3.6.
"""
from opalescence.ui import cli

with open("VERSION") as f:
    version = f.read()

if __name__ == "__main__":
    cli.VERSION = version
    cli.main()
