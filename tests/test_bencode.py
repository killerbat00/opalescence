# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.
"""

from io import BytesIO
from unittest import TestCase

from tests.context import btlib


class TestDecoding(TestCase):
    """
    Test class for opalescence.btlib.bencode
    """

    def test_bdecode_empty_bytes(self):
        """
        Test whether we can decode empty bytes.
        Expected behavior is to get None back from bdecode
        """
        res = btlib.bencode.bdecode(bytes())
        self.assertEquals(res, None)

    def test_bdecode_wrong_types(self):
        """
        Test that we can only decode a bytes-like object.
        Each type of object in bad_types must have len > 0 or bencode will return None
        """
        bad_types = [[1, 2], "string", {"1": "a"}, (1, 2), {1, 2, 3}]
        for t in bad_types:
            with self.subTest(t=t):
                with self.assertRaises(btlib.bencode.DecodeError):
                    btlib.bencode.bdecode(t)

    def test__decode_empty_buffer(self):
        """
        Test that we get None back if an empty buffer makes it to _decode.
        Typically this would be called through bdecode which would realize it's receiving an empty
        object as the data argument and return None
        """
        empty_buf = BytesIO(bytes())
        res = btlib.bencode._decode(empty_buf)
        self.assertEquals(res, None)

    def test__decode_recursion_limit(self):
        """
        Test that we get a BencodeRecursionError if we try to recursively decode an object that is too large
        """
        btlib.bencode.RECURSION_LIMIT = 5  # set to some low value so test run quickly
        buffer = BytesIO(b"d3:one3:one3:one3:one3:one3:one3:one3:onee")
        with self.assertRaises(btlib.bencode.BencodeRecursionError):
            btlib.bencode._decode(buffer)

    def test__decode_empty_list(self):
        self.fail()

    def test__decode_nested_list(self):
        self.fail()

    def test__decode_malformed_list(self):
        self.fail()

    def test__decode_empty_dict(self):
        self.fail()

    def test__decode_nested_dict(self):
        self.fail()

    def test__decode_malformed_dict(self):
        self.fail()

    def test__decode_invalid_char(self):
        self.fail()

    def test__decode_int(self):
        no_delim = bytes(b"14")
        wrong_delim = bytes(b"i14b")
        uneven_delim = bytes(b"i14")
        uneven_delim2 = bytes(b"14e")
        leading_zero = bytes(b"i01e")
        neg_zero = bytes(b"i-0e")

        bad_data = [no_delim, uneven_delim, uneven_delim2, leading_zero, neg_zero, wrong_delim]
        good_data = {-12: bytes(b"i-12e"), 1: bytes(b"i1e"),
                     0: bytes(b"i0e"), -1: bytes(b"i-1e"),
                     100000000: bytes(b"i100000000e"), 99999999: bytes(b"i99999999e")}

        for b in bad_data:
            with self.subTest(b=b):
                with self.assertRaises(btlib.bencode.DecodeError):
                    btlib.bencode._decode_int(BytesIO(b))

        for k, v in good_data.items():
            with self.subTest(k=k):
                self.assertEquals(btlib.bencode._decode_int(BytesIO(v)), k)

    def test__decode_str(self):
        bad_fmt = b"A:aaaaaaaa"
        wrong_delim = b"4-asdf"
        wrong_len_short = b"18:aaaaaaaaaaaaaaaa"
        right_len = b"18:aaaaaaaaaaaaaaaaaa"
        empty_str = b"0:"

        bad_data = [bad_fmt, wrong_delim, wrong_len_short]
        good_data = [right_len, empty_str]

        for b in bad_data:
            with self.subTest(b=b):
                with self.assertRaises(btlib.bencode.DecodeError):
                    btlib.bencode._decode_str(BytesIO(b))

        for b in good_data:
            with self.subTest(b=b):
                self.assertEquals(btlib.bencode._decode_str(BytesIO(b)), b[3:].decode('ISO-8859-1'))

    def test__parse_num(self):
        pass


class TestEncoding(TestCase):
    def test_encoding(self):
        pass
