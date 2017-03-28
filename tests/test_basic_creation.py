#!/usr/bin/env python
# -*- coding: utf-8 -*-

from unittest import TestCase

from tests.context import btlib


class Creation(TestCase):
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
