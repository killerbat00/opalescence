#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests functionality related to opalescence's representation of torrent metainfo files as well
as .torrent file reading, writing and creation from a file or directory
"""
import os
from filecmp import cmp
from shutil import copyfile
from unittest import TestCase

from requests import get

from tests.context import torrent, bencode


class TorrentTest(TestCase):
    """
    Tests the Torrent representation
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = "http://releases.ubuntu.com/16.04/ubuntu-16.04.2-desktop-amd64.iso.torrent"

    @classmethod
    def setUpClass(cls):
        """
        Downloads an ubuntu torrent to use for testing.
        """
        response = get(cls.torrent_url)
        cls.external_torrent_path = os.path.join(cls.external_torrent_path, cls.torrent_url.split("/")[-1])

        if response.status_code == 200:
            file_data = response.content
            with open(cls.external_torrent_path, "wb+") as f:
                f.write(file_data)

    @classmethod
    def tearDownClass(cls):
        """
        Removes the test data directory created for testing
        """
        if os.path.exists(cls.external_torrent_path):
            os.remove(cls.external_torrent_path)

    def test_invalid_path(self):
        """
        Test that an invalid path throws a CreationError
        """
        invalid_path = "Doesn't exist"
        with self.subTest(msg="Invalid path"):
            with self.assertRaises(torrent.CreationError):
                torrent.Torrent.from_file(invalid_path)

    def test_valid_path(self):
        """
        Test that we get a torrent object from a valid path
        """
        with self.subTest(msg="Valid path"):
            self.assertIsInstance(torrent.Torrent.from_file(self.external_torrent_path), torrent.Torrent)

    def test_invalid_torrent_metainfo(self):
        """
        Test that invalid torrent metainfo throws an error
        creates a copy of the externally created .torrent and randomly removes some data from it
        """
        copy_file_name = os.path.join(os.path.dirname(self.external_torrent_path), "test_torrent_copy.torrent")
        copyfile(self.external_torrent_path, copy_file_name)
        file_size = os.path.getsize(copy_file_name)

        with open(copy_file_name, 'wb') as f:
            f.truncate(file_size // 2)

        # the metainfo dictionary is entirely corrupted now, so we should expect a CreationError
        with self.assertRaises(torrent.CreationError):
            torrent.Torrent.from_file(copy_file_name)

        os.remove(copy_file_name)

    def test__gather_files(self):
        """
        Test that we gathered files appropriately
        """
        external_torrent = torrent.Torrent.from_file(self.external_torrent_path)
        filename = ".".join(os.path.basename(self.external_torrent_path).split(".")[:-1])
        for f in external_torrent.files:
            self.assertEqual(f.path, filename)

    def test_properties(self):
        """
        Tests the properties of the torrent metainfo file
        """
        announce_urls = ["http://torrent.ubuntu.com:6969/announce", "http://ipv6.torrent.ubuntu.com:6969/announce"]
        t = torrent.Torrent.from_file(self.external_torrent_path)
        for f in announce_urls:
            self.assertIn(f, t.announce_urls)
        comment = "Ubuntu CD releases.ubuntu.com"
        self.assertEqual(comment, t.comment)
        self.assertIsNone(t.created_by)
        creation_date = 1487289444
        self.assertEqual(creation_date, t.creation_date)
        self.assertFalse(t.private)
        piece_length = 524288
        self.assertEqual(piece_length, t.piece_length)
        self.assertFalse(t.multi_file)

    def test_info_hash(self):
        """
        Tests that the torrent's info hash property returns the correct info hash
        """
        infohash_digest = b"\xdaw^J\xafV5\xefrX:9\x19w\xe5\xedo\x14a~"
        t = torrent.Torrent.from_file(self.external_torrent_path)
        self.assertEqual(infohash_digest, t.info_hash)

    def test_decode_recode_compare(self):
        """
        This should probably live in test_bencode.py, but resides here now since this class creates a .torrent
        metainfo file with an external program

        TODO: move this test to a more proper location
        """
        file_copy = os.path.abspath(os.path.join(os.path.dirname(__file__), "copy.torrent"))

        with open(self.external_torrent_path, 'rb') as f:
            data = f.read()
            unencoded_data = bencode.Decoder(data).decode()

            with open(file_copy, 'wb+') as ff:
                encoded_data = bencode.Encoder(unencoded_data).encode()
                ff.write(encoded_data)

        self.assertTrue(cmp(self.external_torrent_path, file_copy))
        os.remove(file_copy)

    def test_open_file_rewrite(self):
        """
        Tests that we can open an externally created .torrent file, decode it, create a torrent instance,
        then rewrite it into another file. The resulting two files should be equal.
        """
        external_torrent = torrent.Torrent.from_file(self.external_torrent_path)
        file_copy = os.path.abspath(os.path.join(os.path.dirname(__file__), "copy.torrent"))
        external_torrent.to_file(file_copy)
        self.assertTrue(cmp(self.external_torrent_path, file_copy))
        os.remove(file_copy)

    def test_decode_recode_decode_compare(self):
        """
        Decodes a torrent file created using an external program, reencodes that file to a .torrent,
        decodes the resulting torrent and compares its dictionary with the original decoded dictionary
        """
        external_torrent = torrent.Torrent.from_file(self.external_torrent_path)
        original_data = external_torrent.meta_info
        temp_output_filename = os.path.abspath(os.path.join(os.path.dirname(__file__), "copy.torrent"))
        external_torrent.to_file(temp_output_filename)
        new_data = torrent.Torrent.from_file(temp_output_filename).meta_info
        self.assertEqual(original_data, new_data)
        os.remove(temp_output_filename)
