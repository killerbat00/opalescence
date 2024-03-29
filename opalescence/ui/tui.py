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

PROG_NAME = f"Opalescence"
PROG_AND_VERSION = f"Opalescence v{__version__}"
WELCOME_MSG = f"Welcome to {PROG_AND_VERSION}"
SIG_MSG = f"{PROG_NAME} was created by: {__author__} (c) {__year__}"

COLOR_NONE = None
COLOR_INVERTED = None


class WelcomeSplash:
    @staticmethod
    def draw(window, clr):
        height, width = window.getmaxyx()
        content_width = max(len(WELCOME_MSG), len(SIG_MSG)) + 2
        content_height = 4
        pos_x = width // 2 - content_width // 2
        pos_y = height // 2 - content_height // 2

        win = curses.newwin(content_height, content_width, pos_x, pos_y)
        win.border()
        win.bkgd(" ", clr)
        win.addnstr(1, 1, WELCOME_MSG.center(content_width - 2, " "),
                    content_width - 2, clr)
        win.addnstr(2, 1, SIG_MSG.center(content_width - 2, " "),
                    content_width - 2, clr)
        win.refresh()
        time.sleep(1.5)


class HeaderLine:
    @staticmethod
    def draw(window, clr):
        _, width = window.getmaxyx()
        win = curses.newwin(1, width, 0, 0)
        try:
            win.addnstr(0, 0, PROG_AND_VERSION.center(width, " "), width, clr)
        except curses.error:
            pass
        win.refresh()


class FooterLine:
    TORRENT_COMMANDS = {
        "Add": ("a", "(A)dd", lambda x: x),
        "Remove": ("d", "(R)remove", lambda x: x),
        "Files": ("f", "(F)iles", lambda x: x),
        "Info": ("i", "(I)nfo", lambda x: x),
        "Config": ("c", "(C)onfig", lambda x: x),
    }

    APP_COMMANDS = {
        "Settings": ("s", "(S)ettings", lambda x: x),
        "Quit": ("q", "(Q)uit", lambda x: x),
        # "QuitWindow": ("(Q)uit*", lambda x: x)
    }

    @staticmethod
    def draw(window, clr):
        height, width = window.getmaxyx()
        pos_y = height - 1
        win = curses.newwin(1, width, pos_y, 0)
        left = " | ".join(cmd[1] for cmd in FooterLine.TORRENT_COMMANDS.values())
        right = " | ".join(cmd[1] for cmd in FooterLine.APP_COMMANDS.values())

        try:
            win.addnstr(0, 0, left, len(left), clr)
        except curses.error:
            pass
        try:
            win.addnstr(0, width - len(right), right, len(right) + 1, clr)
        except curses.error:
            pass
        win.refresh()


class TorrentList:
    @staticmethod
    def draw(window, clr_none, clr_inv):
        maxy, maxx = window.getmaxyx()
        win = curses.newwin(maxy - 1 - 9, maxx, 1, 0)
        win.border(" ", " ", 0, " ", curses.ACS_HLINE, curses.ACS_HLINE, " ", " ")

        win.addnstr(0, 0, "Name", 4, clr_none)
        win.addnstr(0, 50, "Up/Down (kbps)", 14, clr_none)
        win.addnstr(0, 70, "% Complete", 10, clr_none)

        t1name = "ubuntu-20.10-desktop-amd64.iso.torrent"
        clr_downloading = curses.color_pair(3)
        win.addnstr(1, 0, t1name, len(t1name), clr_downloading)
        t1speed = "73/1,375"
        win.addnstr(1, 50, t1speed, len(t1speed), clr_downloading)
        win.addnstr(1, 70, "68.01", len("68.01"), clr_downloading)

        t2name = "AlpineLinux-2021.torrent"
        clr_seeding = curses.color_pair(4)
        win.addnstr(2, 0, t2name, len(t2name), clr_seeding)
        t2speed = "748/10"
        win.addnstr(2, 50, t2speed, len(t2speed), clr_seeding)
        win.addnstr(2, 70, "100", len("100"), clr_seeding)

        t3name = "Project-Gutenberg-bak-2020.torrent"
        clr_error = curses.color_pair(5)
        win.addnstr(3, 0, t3name, len(t3name), clr_error)
        t3speed = "!!/!!"
        win.addnstr(3, 50, t3speed, len(t3speed), clr_error)
        win.addnstr(3, 70, "!!!", len("!!!"), clr_error)

        t4name = "ubuntu-18.04-desktop-amd64.iso.torrent"
        win.addnstr(4, 0, t4name, len(t4name), clr_none)
        t4speed = "0/0"
        win.addnstr(4, 50, t4speed, len(t4speed), clr_none)
        win.addnstr(4, 70, "58.2", len("58.2"), clr_none)

        win.refresh()


class MainScreen:
    @staticmethod
    def draw(window, clr_none, clr_inv):
        HeaderLine.draw(window, clr_inv)
        TorrentList.draw(window, clr_none, clr_inv)
        InfoSection.draw(window, clr_inv)
        FooterLine.draw(window, clr_inv)


class InfoSection:
    @staticmethod
    def draw(window, clr_inv):
        maxy, maxx = window.getmaxyx()
        win = curses.newwin(9, maxx, maxy - 10, 0)
        win.border(" ", " ", 0, " ", curses.ACS_HLINE, curses.ACS_HLINE, " ", " ")
        win.addnstr(0, 0, "Info", 4, clr_inv)
        win.refresh()


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
        curses.curs_set(False)
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)
        curses.init_pair(3, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_RED, curses.COLOR_BLACK)
        self.color_none = curses.color_pair(1)
        self.color_inverted = curses.color_pair(2)

        WelcomeSplash.draw(self.root_win, self.color_inverted)
        curses.flushinp()
        self.root_win.clear()
        self.root_win.refresh()
        MainScreen.draw(self.root_win, self.color_none, self.color_inverted)
        self.root_win.getch()
        curses.curs_set(True)


def start(args):
    """
    TUI entry point
    """
    tui = OplTui()
    curses.wrapper(tui.main)
