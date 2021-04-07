# -*- coding: utf-8 -*-

"""
Package containing the main opalescence application logic.
"""

__author__ = """Brian Houston Morrow"""
__email__ = "bhm@brianmorrow.net"
__version__ = "0.4.1"
__year__ = "2021"

import dataclasses


@dataclasses.dataclass
class AppConfig:
    use_cli: bool


_AppConfig = AppConfig(False)


def get_app_config():
    return _AppConfig
