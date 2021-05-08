# -*- coding: utf-8 -*-

"""
Terminal User Interface for Opalescence
"""
import curses
import curses.ascii
import functools
import logging
import time

from opalescence import __version__, __year__, __author__

logger = logging.getLogger("opalescence")

PROG_NAME = f"Opalescence v{__version__}"
WELCOME_MSG = f"Welcome to {PROG_NAME}"
SIG_MSG = f"{PROG_NAME} was created by: {__author__} (c) {__year__}"

COLOR_NONE = None
COLOR_INVERTED = None


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


class FooterLine:
    TORRENT_COMMANDS = {
        "Add": ("(A)dd", lambda x: x),
        "Delete": ("(D)elete", lambda x: x),
        "Files": ("(F)iles", lambda x: x),
        "Config": ("(C)onfig", lambda x: x),
    }

    APP_COMMANDS = {
        "Settings": ("(S)ettings", lambda x: x),
        "Quit": ("(Q)uit", lambda x: x),
        # "QuitWindow": ("(Q)uit*", lambda x: x)
    }

    @staticmethod
    def draw(window, clr):
        width = curses.COLS
        pos_y = curses.LINES - 1
        left = " | ".join(cmd[0] for cmd in FooterLine.TORRENT_COMMANDS.values())
        window.addnstr(pos_y, 0, left, len(left), clr)
        right = " | ".join(cmd[0] for cmd in FooterLine.APP_COMMANDS.values())

        try:
            window.addnstr(pos_y, width - len(right), right, len(right) + 1, clr)
        except curses.error:
            pass


class MainScreen:
    @staticmethod
    def draw(window, clr_none, clr_inv):
        window.clear()
        window.border()
        HeaderLine.draw(window, clr_inv)
        FooterLine.draw(window, clr_inv)
        window.refresh()


class Command:
    def __init__(self, name, func):
        self.name = name
        self.func = func


class OplTui:
    def __init__(self):
        self.color_none = None
        self.color_inverted = None
        # self.cmds: list[Command] = []
        self.root_win = None

    def main(self, root):
        self.root_win = root

        curses.curs_set(0)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
        self.color_none = curses.color_pair(1)
        self.color_inverted = curses.color_pair(2)

        self.root_win.clear()
        WelcomeSplash.draw(self.root_win, self.color_inverted)
        MainScreen.draw(self.root_win, self.color_none, self.color_inverted)
        curses.flushinp()
        self.root_win.getch()
        curses.curs_set(1)


def start(args):
    """
    TUI entry point
    """
    tui = OplTui()
    curses.wrapper(functools.partial(tui.main))
