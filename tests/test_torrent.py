#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Tests functionality related to opalescence's representation of torrent metainfo files as well
as .torrent file reading, writing and creation from a file or directory
"""
import os
import subprocess
from filecmp import cmp
from shutil import rmtree, copyfile
from time import time
from unittest import TestCase, skip

from tests.context import btlib


class Transmission:
    """
    Represents the transmission command used to create_torrent a .torrent file from 'randomly' generated data.
    """

    def __init__(self):
        self.prog_root = """C:\Program Files (x86)\Transmission"""
        self.prog_name = "transmission-create.exe"
        self.program = os.path.join(self.prog_root, self.prog_name)

    def create_torrent(self, from_dir: str, dest_filename: str, comment: str, tracker: str):
        """
        Asks Transmission to create_torrent a .torrent file

        :param from_dir:      directory from which to create_torrent the .torrent
        :param dest_filename: destination filename of the torrent
        :param comment:       torrent comment
        :param tracker:       tracker URL
        :return:              True on succes, False otherwise
        """
        cmd = [self.program, "-o", dest_filename, "-c", comment, "-t", tracker, from_dir]
        try:
            subprocess.run(cmd)
        except subprocess.SubprocessError:
            # log, etc
            return False
        return True


class TorrentTest(TestCase):
    """
    Tests the Torrent representation
    """
    test_torrent_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "test_torrent_data"))
    external_torrent_filename = os.path.join(test_torrent_data_dir, "test_torrent.torrent")
    my_external_torrent_filename = os.path.join(test_torrent_data_dir, "my_test_torrent.torrent")
    tracker = "http://www.brianmorrow.net/faketracker"
    comment = "This is some dang comment!"

    @classmethod
    def setUpClass(cls):
        """
        Sets up the test cases. This creates a temporary directory of files containing random data.
        This directory is used to create_torrent a torrent in an external program. We use this .torrent throughout
        the tests

        TODO: generate the data more randomly
        """
        if os.path.exists(cls.test_torrent_data_dir):
            rmtree(cls.test_torrent_data_dir)

        os.mkdir(cls.test_torrent_data_dir)
        for x in range(5):  # number of files
            with open(os.path.join(cls.test_torrent_data_dir, f"Test file {x}" + str(int(time()))), "w+") as f:
                for y in range(16):
                    f.write("This is random data?\nYEAH RIGHT\n" * 2 ** y)

        transmission_cmd = Transmission()
        if not transmission_cmd.create_torrent(cls.test_torrent_data_dir, cls.external_torrent_filename,
                                               cls.comment, cls.tracker):
            raise RuntimeError("Unable to create_torrent torrent file from transmission.")

    @classmethod
    def tearDownClass(cls):
        """
        Removes the test data directory created for testing
        """
        if os.path.exists(cls.test_torrent_data_dir):
            rmtree(cls.test_torrent_data_dir)

    def test_invalid_path(self):
        """
        Test that an invalid path throws a CreationError
        """
        invalid_path = "Doesn't exist"
        with self.subTest(msg="Invalid path"):
            with self.assertRaises(btlib.torrent.CreationError):
                btlib.torrent.Torrent.from_file(invalid_path)

    def test_invalid_torrent_metainfo(self):
        """
        Test that invalid torrent metainfo throws an error

        creates a copy of the externally created .torrent and randomly removes some data from it
        """
        copy_file_name = os.path.join(TorrentTest.test_torrent_data_dir, "test_torrent_copy.torrent")
        copyfile(TorrentTest.external_torrent_filename, copy_file_name)
        file_size = os.path.getsize(copy_file_name)

        with open(copy_file_name, 'wb') as f:
            f.truncate(file_size // 2)

        # the metainfo dictionary is entirely corrupted now, so we should expect a DecodeError
        with self.assertRaises(btlib.bencode.DecodeError):
            btlib.torrent.Torrent.from_file(copy_file_name)

        os.remove(copy_file_name)

    @skip("Not ready")
    def test__gather_files(self):
        """
        Test that we gathered files appropriately
        """
        self.fail()

    @skip("Not ready")
    def test__pieces(self):
        """
        Test that we are piecing things out appropriately
        """
        self.fail()

    @skip("Not ready")
    def test_files(self):
        """
        Test the list of files used for the torrent's data
        """
        self.fail()

    @skip("Not ready")
    def test_properties(self):
        """
        Tests the properties of the torrent metainfo file
        """
        # single announce url
        # multiple announce urls
        # comment
        # no comment
        # created_by
        # no created_by
        # private
        # public
        # pieces
        # piece_length
        # total_size
        self.fail()

    def test_decode_recode_compare(self):
        """
        This should probably live in test_bencode.py, but resides here now since this class creates a .torrent
        metainfo file with an external program

        TODO: move this test to a more proper location
        """
        with open(TorrentTest.external_torrent_filename, 'rb') as f:
            data = f.read()
            unencoded_data = btlib.bencode.Decoder().decode(data)

            with open(TorrentTest.my_external_torrent_filename, 'wb+') as ff:
                encoded_data = btlib.bencode.Encoder().bencode(unencoded_data)
                ff.write(encoded_data)

        self.assertTrue(cmp(TorrentTest.external_torrent_filename, TorrentTest.my_external_torrent_filename))
        os.remove(TorrentTest.my_external_torrent_filename)

    def test_open_file_rewrite(self):
        """
        Tests that we can open an externally created .torrent file, decode it, create a torrent instance,
        then rewrite it into another file. The resulting two files should be equal.
        """
        transmission_torrent = btlib.torrent.Torrent.from_file(TorrentTest.external_torrent_filename)
        temp_output_filename = os.path.join(TorrentTest.test_torrent_data_dir, "test_torrent_rewritten.torrent")
        transmission_torrent.to_file(temp_output_filename)
        self.assertTrue(cmp(TorrentTest.external_torrent_filename, temp_output_filename))

    def test_decode_recode_decode_compare(self):
        """
        Decodes a torrent file created using an external program, reencodes that file to a .torrent,
        decodes the resulting torrent and compares its dictionary with the original decoded dictionary
        """
        transmission_torrent = btlib.torrent.Torrent.from_file(TorrentTest.external_torrent_filename)
        original_data = transmission_torrent.meta_info
        temp_output_filename = os.path.join(TorrentTest.test_torrent_data_dir, "test_torrent_rewritten.torrent")
        transmission_torrent.to_file(temp_output_filename)
        new_data = btlib.torrent.Torrent.from_file(temp_output_filename).meta_info
        self.assertEqual(original_data, new_data)
