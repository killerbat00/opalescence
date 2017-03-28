# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.
"""
from collections import OrderedDict
from io import BytesIO
from unittest import TestCase

from tests.context import btlib

btlib.bencode._reset_recursion_counters()


class Decoding(TestCase):
    """
    Test class for opalescence.btlib.bencode and functions into which it calls.
    """

    def setUp(self):
        btlib.bencode._reset_recursion_counters()

    def test_empty_values(self):
        """
        Ensure bdecode and _decode handle empty values properly
        """
        empty_bytes = ("empty bytes", bytes(), None)
        with self.subTest(msg=f"bdecode {empty_bytes[0]}"):
            self.assertEquals(btlib.bencode.bdecode(empty_bytes[1]), empty_bytes[2])

        with self.subTest(msg=f"_decode {empty_bytes[0]}"):
            with self.assertRaises(AttributeError):
                btlib.bencode._decode(empty_bytes[1]), empty_bytes[2]

        empty_buffer = ("empty buffer", BytesIO(empty_bytes[1]), None)
        empty_list = ("empty list", BytesIO(b"le"), [])
        empty_dict = ("empty dict", BytesIO(b"de"), OrderedDict())
        non_errors = [empty_buffer, empty_list, empty_dict]

        for case in non_errors:
            with self.subTest(msg=f"_decode {case[0]}"):
                self.assertEquals(btlib.bencode._decode(case[1]), case[2])

        empty_int = ("empty int", BytesIO(b"ie"), btlib.bencode.DecodeError)
        invalid_str = ("empty string", BytesIO(b"3:"), btlib.bencode.DecodeError)
        only_delim = ("only delim", BytesIO(b":"), btlib.bencode.DecodeError)
        errors = [empty_int, invalid_str, only_delim]

        btlib.bencode._reset_recursion_counters()
        for case in errors:
            with self.subTest(msg=f"_decode {case[0]}"):
                with self.assertRaises(case[2]):
                    btlib.bencode._decode(case[1])

    def test_bdecode_wrong_types(self):
        """
        Test that we can only decode a bytes-like object.
        Each type of object in bad_types must have len > 0 or bencode will return None
        """
        bad_types = [[1, 2], "string", {"1": "a"}, (1, 2), {1, 2, 3}]
        for t in bad_types:
            with self.subTest(msg=f"bdecode {t}"):
                with self.assertRaises(btlib.bencode.DecodeError):
                    btlib.bencode.bdecode(t)

    def test__decode_imbalanced_delims(self):
        """
        Tests that _decode handles imbalanced delimiters
        imbalanced beginning delimiters are invalid
        imbalanced ending delimiters are ignored
        """

        missing_start_delim = ("Missing start delim", BytesIO(b"3:onee"), "one")
        ambigouos_end_delim = ("Ambiguous end delim", BytesIO(b"d3:one9:list itemee"), OrderedDict(one="list item"))
        list_extra_end_delim = ("List extra end delim", BytesIO(b"l3:oneeeee"), ["one"])
        list_extra_end_delim_with_list = ("List extra end delim with list", BytesIO(b"l3:oneeleeee"), ["one"])
        dict_extra_end_delim = ("Dict extra end delim", BytesIO(b"d3:num3:valeeee"), OrderedDict(num="val"))
        dict_extra_end_delim_with_list = (
        "Dict extra end delim with list", BytesIO(b"d3:num3:valeeelee"), OrderedDict(num="val"))

        for k, v in locals().items():
            if k != 'self':
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEquals(btlib.bencode._decode(v[1]), v[2])

    def test__decode_recursion_limit(self):
        """
        Test that we get a BencodeRecursionError if we try to recursively decode an object that is too large
        """
        btlib.bencode.RECURSION_LIMIT = 5  # set to some low value so test run quickly
        buffer = BytesIO(b"d3:one3:one3:one3:one3:one3:one3:one3:onee")
        with self.assertRaises(btlib.bencode.BencodeRecursionError):
            btlib.bencode._decode(buffer)
        btlib.bencode._reset_recursion_counters()

    def test__decode_consecutive_lists(self):
        """
        Tests that _decode can handle consecutive lists

        _decode will return a single list when consecutive lists are given
        even if one of those lists contains some data then empty lists
        if an empty list is encountered in a list with data after it, that data is not returned
        """
        cons_lists = ("Consecutive lists", BytesIO(b"lelelelelele"), [])
        cons_lists_pop = ("Consecutive lists w/ populated", BytesIO(b"l3:vallee"), ["val"])
        cons_lists_with_dict = ("Consecutive lists w/ dict value", BytesIO(b"lde3:vale"), [])
        cons_lists_pre_data = ("Consecutive lists before data", BytesIO(b"llelele3:vale"), [])

        for k, v in locals().items():
            if k != "self":
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEquals(btlib.bencode._decode(v[1]), v[2])

    def test__decode_nested_list(self):
        """
        Tests that _decode can handle a nested list

        _decode will return a single list when empty lists are nested
        _decode will return nested lists if the innermost is populated, otherwise it will only recurse to the first
        list with data
        """
        empty_nest = ("Empty nested lists", BytesIO(b"llleee"), [])
        pop_list = ("Populated nested list", BytesIO(b"ll3:valee"), [["val"]])
        nested_pop_list = ("Nested populated list", BytesIO(b"lll3:valeee"), [[["val"]]])
        pop_list_nested = ("Populated list w/ trailing nested empty lists", BytesIO(b"ll3:oneleee"), [["one"]])

        for k, v in locals().items():
            if k != "self":
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEquals(btlib.bencode._decode(v[1]), v[2])

    def test__decode_consecutive_dicts(self):
        """
        Tests that _decode can handle consecutive dicts
        _decode will return a single dict when consecutive dicts are given
        even if one of those dicts contains data then empty lists
        if an empty list is encountered in a dict with data after it, that data is not returned
        """
        cons_dicts = ("Consecutive dicts", BytesIO(b"dedededede"), OrderedDict())
        populated_cons = ("Populated consecutive dicts", BytesIO(b"d3:num3:valede"), OrderedDict(num="val"))
        populated_empty_key = ("Dict with empty key", BytesIO(b"dle3:num3:vale"), OrderedDict())

        for k, v in locals().items():
            if k != "self":
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEquals(btlib.bencode._decode(v[1]), v[2])

    def test__decode_nested_dict(self):
        """
        Tests that _decode can handle a nested dict

        _decode will return a single dict when empty dicts are nested
        dictionaries can not be keys of dictionaries
        """
        empty = BytesIO(b"dddeee")
        res = btlib.bencode._decode(empty)
        self.assertEquals(res, OrderedDict())

    def test__decode_invalid_char(self):
        """
        Tests that _decode can handle an invalid character

        dicts can only contain string or integer keys and dict, string, list, integer values
        list can only contain string, integer, list, or
        """
        err = btlib.bencode.DecodeError
        invalid_char = ("Invalid character", BytesIO(b"?"), err)
        invalid_key_dict = ("Invalid dict key", BytesIO(b"d?e"), err)
        empty_key_dict = ("Empty dict key", BytesIO(b"d3:e"), err)
        invalid_val_list = ("Invalid list value", BytesIO(b"l?e"), err)

        for k, v in locals().items():
            if k not in ["self", "err"]:
                with self.subTest(msg=f"_decode {v[0]}"):
                    with self.assertRaises(v[2]):
                        btlib.bencode._decode(v[1])

    def test__decode_int(self):
        """
        Tests that the _decode_int function handles properly and improperly formatted bencoded integer data
        """
        no_delim = bytes(b"14")
        wrong_delim = bytes(b"i14b")
        uneven_delim = bytes(b"i14")
        uneven_delim2 = bytes(b"14e")
        leading_zero = bytes(b"i01e")
        neg_zero = bytes(b"i-0e")
        string = bytes(b"istringe")

        bad_data = [no_delim, uneven_delim, uneven_delim2, leading_zero, neg_zero, wrong_delim, string]
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
        """
        Tests that the _decode_str function handles properly and improperly formatted data
        """
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
