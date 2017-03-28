#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
from unittest import TestCase

from tests.context import btlib


class TransmissionCommand:
    def __init__(self):
        self.prog_root = """C:\Program Files (x86)\Transmission"""
        self.prog_name = "transmission-create.exe"
        self.program = os.path.join(self.prog_root, self.prog_name)


class BasicCreation(TestCase):
    def setUp(self):
        pass

    def test_obj_creation_from_external_file(self):
        """
        Test that we can create a torrent metainfo object from a .torrent file created with an external program.
        Currently, this uses a torrent file created by Transmission
        """
        # check for transmission torrent file
        # if missing
        #   check for test data directory
        #       create if missing
        #   use transmission to generate torrent file
        # generate btlib.torrent.Torrent object from transmission file
        # ensure btlib.torent.CreationError isn't thrown
        self.fail()

    def test_obj_creation_from_dir(self):
        """
        Test that we can create a torrent metainfo object from a directory of test data.
        This directory of test data should be the same used when creating a .torrent file with an external program.
        """
        # check for my test torrent file
        # create from directory if missing
        # check for transmission torrent file
        # if missing
        #   generate
        # generate btlib.torrent.Torrent object from transmission file
        #
        # compare my torrent file object to transmission file's
        self.fail()

    def test_decode_recode_decode_compare(self):
        """
        Decodes a torrent file created using qbittorrent, reencodes that file to a .torrent,
        decodes the resulting torrent and compares its dictionary with the original decoded
        from qbittorrent data
        """
        qbt_input = ""
        qbt_output = ""

        qbittorrent_file = btlib.torrent.Torrent.from_file(qbt_input)
        qbittorrent_file.to_file(qbt_output)
        my_file = btlib.torrent.Torrent.from_file(qbt_output)
        q_obj = qbittorrent_file._to_obj()
        my_obj = my_file._to_obj()
        self.assertEquals(q_obj, my_obj)

    def test_path_to_torrent(self):
        """
        Creates a torrent from a path of files.
        Also creates a torrent object from a qbittorrent metainfo file created for the same files.
        Expects the metainfo of the two to be the same.
        """
        path = ""
        qbt_file = ""
        trackers = []
        my_from_dir = btlib.torrent.Torrent.from_path(path, trackers, comment="this is a comment")
        qbt_from_dir = btlib.torrent.Torrent.from_file(qbt_file)
        self.assertEquals(my_from_dir.info_hash, qbt_from_dir.info_hash)
