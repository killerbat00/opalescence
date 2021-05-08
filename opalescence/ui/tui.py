# -*- coding: utf-8 -*-

"""
Terminal User Interface for Opalescence
"""
import curses
import curses.ascii
import logging
import time

from opalescence import __version__, __year__, __author__

logger = logging.getLogger("opalescence")

PROG_NAME = f"Opalescence v{__version__}"
WELCOME_MSG = f"Welcome to {PROG_NAME}"
SIG_MSG = f"{PROG_NAME} was created by: {__author__} (c) {__year__}"


class WelcomeSplash:
    @staticmethod
    def draw(window, clr):
        width, height = curses.COLS, curses.LINES
        content_width = max(len(WELCOME_MSG), len(SIG_MSG)) + 2
        content_height = 4
        pos_x = width // 2 - content_width // 2
        pos_y = height // 2 - content_height // 2

        win = curses.newwin(content_height, content_width, pos_x, pos_y)
        win.bkgd(" ", clr)
        win.border()
        win.addnstr(1, 1, WELCOME_MSG.center(content_width - 2, " "),
                    content_width - 2, clr)
        win.addnstr(2, 1, SIG_MSG.center(content_width - 2, " "),
                    content_width - 2, clr)
        win.overwrite(window)
        window.refresh()
        time.sleep(2)


class HeaderLine:
    @staticmethod
    def draw(window, clr):
        width = curses.COLS
        window.addnstr(0, 0, PROG_NAME.center(width, " "), width, clr)


class MainScreen:
    @staticmethod
    def draw(window, clr_none, clr_inv):
        window.clear()
        window.border()
        HeaderLine.draw(window, clr_inv)
        window.refresh()


COLOR_NONE = None
COLOR_INVERTED = None


def main(root):
    global COLOR_NONE, COLOR_INVERTED
    curses.curs_set(0)
    curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
    COLOR_NONE = curses.color_pair(1)
    COLOR_INVERTED = curses.color_pair(2)
    root.clear()
    WelcomeSplash.draw(root, COLOR_INVERTED)
    MainScreen.draw(root, COLOR_NONE, COLOR_INVERTED)
    curses.flushinp()
    root.getch()
    root.clear()
    curses.curs_set(1)


def start(args):
    """
    TUI entry point
    """
    curses.wrapper(main)
