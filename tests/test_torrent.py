# -*- coding: utf-8 -*-

"""
Tests functionality related to opalescence's representation of torrent metainfo files as well
as .torrent file reading, writing and creation from a file or directory
"""
import os
from collections import OrderedDict
from filecmp import cmp
from shutil import copyfile
from unittest import TestCase

from btproto import bencode
from requests import get

from opalescence.btlib import metainfo
from tests.context import torrent_url


class TestTorrent(TestCase):
    """
    Tests the Torrent representation.
    """
    external_torrent_path = os.path.abspath(os.path.dirname(__file__))
    torrent_url = torrent_url

    @classmethod
    def setUpClass(cls):
        """
        Downloads an ubuntu torrent to use for testing.
        """
        cls.external_torrent_path = os.path.join(cls.external_torrent_path, cls.torrent_url.split("/")[-1])
        if not os.path.exists(cls.external_torrent_path):
            r = get(cls.torrent_url)
            if r.status_code == 200:
                file_data = r.content
                with open(cls.external_torrent_path, "wb+") as f:
                    f.write(file_data)

    def test_invalid_path(self):
        """
        Test that an invalid path log_and_raise a CreationError.
        """
        invalid_path = "Doesn't exist"
        with self.subTest(msg="Invalid path"):
            with self.assertRaises(metainfo.CreationError):
                metainfo.MetaInfoFile.from_file(invalid_path)

    def test_valid_path(self):
        """
        Test that we get a torrent object from a valid path.
        """
        with self.subTest(msg="Valid path"):
            self.assertIsInstance(
                metainfo.MetaInfoFile.from_file(self.external_torrent_path),
                metainfo.MetaInfoFile)

    def test_invalid_torrent_metainfo(self):
        """
        Test that invalid torrent metainfo log_and_raise an error.
        creates a copy of the externally created .torrent and randomly removes some data from it.
        """
        copy_file_name = os.path.join(os.path.dirname(self.external_torrent_path), "test_torrent_copy.torrent")
        copyfile(self.external_torrent_path, copy_file_name)
        file_size = os.path.getsize(copy_file_name)

        with open(copy_file_name, 'wb') as f:
            f.truncate(file_size // 2)

        # the metainfo dictionary is entirely corrupted now, so we should expect a CreationError
        with self.assertRaises(metainfo.CreationError):
            metainfo.MetaInfoFile.from_file(copy_file_name)

        os.remove(copy_file_name)

    def test__gather_files(self):
        """
        Test that we gathered files appropriately.
        """
        external_torrent = metainfo.MetaInfoFile.from_file(
            self.external_torrent_path)
        filename = ".".join(os.path.basename(self.external_torrent_path).split(".")[:-1])
        for f in external_torrent.files:
            self.assertEqual(f.path, filename)

    def test_properties(self):
        """
        Tests the properties of the torrent metainfo file.
        """
        announce_urls = ["http://torrent.ubuntu.com:6969/announce", "http://ipv6.torrent.ubuntu.com:6969/announce"]
        t = metainfo.MetaInfoFile.from_file(self.external_torrent_path)
        for f in announce_urls:
            self.assertIn(f, t.announce_urls)
        comment = "Ubuntu CD releases.ubuntu.com"
        self.assertEqual(comment, t.comment)
        self.assertIsNone(t.created_by)
        creation_date = 1519934077
        self.assertEqual(creation_date, t.creation_date)
        self.assertFalse(t.private)
        piece_length = 524288
        self.assertEqual(piece_length, t.piece_length)
        self.assertFalse(t.multi_file)

    def test_info_hash(self):
        """
        Tests that the torrent's info hash property returns the correct info hash.
        """
        infohash_digest= b"w\x8c\xe2\x80\xb5\x95\xe5w\x80\xff\x08?.\xb6\xf8\x97\xdf\xa4\xa4\xee"
        t = metainfo.MetaInfoFile.from_file(self.external_torrent_path)
        self.assertEqual(infohash_digest, t.info_hash)

    def test_decode_recode_compare(self):
        """
        This should probably live in test_bencode.py, but resides here now since this class creates a .torrent
        metainfo file with an external program.

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
        external_torrent = metainfo.MetaInfoFile.from_file(
            self.external_torrent_path)
        file_copy = os.path.abspath(os.path.join(os.path.dirname(__file__), "copy.torrent"))
        external_torrent.to_file(file_copy)
        self.assertTrue(cmp(self.external_torrent_path, file_copy))
        os.remove(file_copy)

    def test_decode_recode_decode_compare(self):
        """
        Decodes a torrent file created using an external program, reencodes that file to a .torrent,
        decodes the resulting torrent and compares its dictionary with the original decoded dictionary.
        """
        external_torrent = metainfo.MetaInfoFile.from_file(
            self.external_torrent_path)
        original_data = external_torrent.meta_info
        temp_output_filename = os.path.abspath(os.path.join(os.path.dirname(__file__), "copy.torrent"))
        external_torrent.to_file(temp_output_filename)
        new_data = metainfo.MetaInfoFile.from_file(
            temp_output_filename).meta_info
        self.assertEqual(original_data, new_data)
        os.remove(temp_output_filename)

    def test__validate_torrent_dict(self):
        """
        Tests that _validate_torrent_dict accepts and rejects torrent metainfo dictionaries correctly.
        """
        no_keys = OrderedDict()
        missing_key = OrderedDict({b"announce": b"val"})
        missing_info_key = OrderedDict(
            {b"announce": b"val", b"info": OrderedDict({b"pieces": b"00000000000000000000", b"piece length": 16384})})
        invalid_pieces_length = OrderedDict(
            {b"announce": b"val",
             b"info": OrderedDict({b"name": b"name", b"pieces": b"0", b"piece length": 16384})})
        missing_length = OrderedDict(
            {b"announce": b"val", b"info": OrderedDict({b"name": b"name", b"pieces": b"00000000000000000000",
                                                        b"piece length": 16384})})
        missing_file_list = OrderedDict({b"announce": b"val", b"info": OrderedDict(
            {b"files": [], b"name": b"name", b"pieces": b"00000000000000000000", b"piece length": 16384})})
        invalid_file_list = OrderedDict({b"announce": b"val", b"info": OrderedDict(
            {b"files": [OrderedDict({b"length": 12})], b"name": b"name", b"pieces": b"00000000000000000000",
             b"piece length": 16384})})

        bad_data = [no_keys, missing_key, missing_info_key, invalid_pieces_length, missing_length, missing_file_list,
                    invalid_file_list]
        for b in bad_data:
            with self.subTest(b=b):
                with self.assertRaises(metainfo.CreationError):
                    metainfo._validate_torrent_dict(b)
