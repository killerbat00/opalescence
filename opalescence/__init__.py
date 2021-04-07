# -*- coding: utf-8 -*-

"""
Package containing the main opalescence application logic.
"""

__author__ = """Brian Houston Morrow"""
__email__ = "bhm@brianmorrow.net"
__version__ = "0.5.0"
__year__ = "2021"

import dataclasses


# TODO: Remove ASAP
@dataclasses.dataclass
class AppConfig:
    use_cli: bool = False
    update_sec: int = 2
    max_peers: int = 2


_AppConfig = AppConfig()


def get_app_config():
    return _AppConfig
