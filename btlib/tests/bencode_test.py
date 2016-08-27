# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.

author: brian houston morrow
"""
from io import BytesIO
from unittest import TestCase

from btlib.bencode import DecodeError


class TestDecoding(TestCase):
    def test_bdecode_empty_bytes(self):
        from btlib.bencode import bdecode
        res = bdecode(bytes())
        self.assertEquals(res, None)

    def test_bdecode_types(self):
        from btlib.bencode import bdecode, DecodeError
        bad_types = [list, str, dict, int, tuple, set]
        for t in bad_types:
            with self.subTest(t=t):
                with self.assertRaises(DecodeError):
                    bdecode(t())

    def test__decode_int(self):
        from btlib.bencode import _decode_int
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
                with self.assertRaises(DecodeError):
                    _decode_int(BytesIO(b))

        for k, v in good_data.items():
            with self.subTest(k=k):
                self.assertEquals(_decode_int(BytesIO(v)), k)

    def test__decode_str(self):
        from btlib.bencode import _decode_str
        bad_fmt = b"A:aaaaaaaa"
        wrong_delim = b"4-asdf"
        wrong_len_short = b"18:aaaaaaaaaaaaaaaa"
        right_len = b"18:aaaaaaaaaaaaaaaaaa"
        empty_str = b"0:"

        bad_data = [bad_fmt, wrong_delim, wrong_len_short]
        good_data = [right_len, empty_str]

        for b in bad_data:
            with self.subTest(b=b):
                with self.assertRaises(DecodeError):
                    _decode_str(BytesIO(b))

        for b in good_data:
            with self.subTest(b=b):
                self.assertEquals(_decode_str(BytesIO(b)), b[3:].decode('ISO-8859-1'))

    def test__parse_num(self):
        pass

    def test_bdecode(self):
        self.fail()


class TestEncoding(TestCase):
    def test_encoding(self):
        pass
