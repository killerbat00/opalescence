# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.

author: brian houston morrow
"""
from unittest import TestCase

from btlib.bencode import *


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
        uneven_delim = bytes(b"i14")
        uneven_delim2 = bytes(b"14e")
        leading_zero = bytes(b"i01e")
        neg_zero = bytes(b"i-0e")
        neg_nonzero = bytes(b"i-12e")

        bad_data = [no_delim, uneven_delim, uneven_delim2, leading_zero, neg_zero]
        good_data = [neg_nonzero]

        for b in bad_data:
            with self.subTest(b=b):
                with self.assertRaises(DecodeError):
                    _decode_int(BytesIO(b))

    def test_bdecode(self):
        self.fail()


class TestEncoding(TestCase):
    def test_encoding(self):
        pass
