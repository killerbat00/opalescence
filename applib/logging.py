# -*- coding: utf-8 -*-

"""
Provides support for application level logging initialization

author: brian houston morrow
"""

import logging
import sys


def get_logger(name: str) -> logging.Logger:
    """
    Returns the root logger for the application. May eventually be used to handle logging to separate destinations.
    :param name: name of the root logger
    :return:     Logger instance
    """
    sh = logging.StreamHandler(stream=sys.stdout)
    f = logging.Formatter(fmt="{asctime} : {name} : [{levelname}] {message}", datefmt="%m/%d/%Y %H:%M:%S", style="{")

    sh.setFormatter(f)
    root = logging.getLogger(name)
    root.setLevel(logging.DEBUG)
    root.addHandler(sh)
    return root
