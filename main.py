# !/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Opalescence is a simple torrent client.
"""

import argparse
import logging
import logging.config
import os
import unittest


def create_logger():
    """
    Creates and configures the root logger
    Configuration is pulled from config/logging.ini
    """
    full_path = os.path.realpath(__file__)
    dirname = os.path.dirname(full_path)
    log_conf_path = os.path.join(dirname, "config", "logging.ini")
    logging.config.fileConfig(log_conf_path)
    logging.info("Initialized logging")


def create_argparser() -> argparse.ArgumentParser:
    """
    Initializes the root argument parser and all relevant subparsers for supported commands.
    :return:    argparse.ArgumentParser instance
    """
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    test_parser = subparsers.add_parser("test", help="Run the test suite")
    test_parser.set_defaults(func=run_tests)

    return parser


def main():
    """
    Main entry-point into Opalescence.
    """
    create_logger()
    logging.info("Initializing argument parser and subparsers")
    argparser = create_argparser()

    try:
        args = argparser.parse_args()
        args.func(args)
    except AttributeError:
        logging.debug("Program invoked with no arguments")
        argparser.print_help()


def run_tests(_) -> None:
    """
    Runs the test suite found in the tests/ directory
    :param _: unused
    """
    logging.debug("Running the test suite")

    loader = unittest.defaultTestLoader
    runner = unittest.TextTestRunner()
    suite = loader.discover(os.path.abspath(os.path.join(os.path.dirname(__file__), "tests")))
    runner.run(suite)


if __name__ == '__main__':
    main()
    logging.shutdown()
