# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.
"""
from collections import OrderedDict
from io import BytesIO
from unittest import TestCase

from tests.context import bencode


class Decoder(TestCase):
    """
    Test class for opalescence.Decoder
    """

    def test_creation(self):
        """
        Ensure __init__ works properly
        """
        decoder = bencode.Decoder()
        self.assertIsInstance(decoder, bencode.Decoder)
        self.assertEqual(decoder.recursion_limit, 1000)
        self.assertEqual(decoder.current_iter, 0)

    def test_recursion_limit_creation(self):
        """
        Ensure we can customize the reucrsion limit
        """
        bad_limits = [-1, 0]
        good_limits = [2, 5, 10, 999999999]

        for limit in bad_limits:
            with self.assertRaises(bencode.DecodeError):
                bencode.Decoder(recursion_limit=limit)

        for limit in good_limits:
            decoder = bencode.Decoder(recursion_limit=limit)
            self.assertEqual(decoder.recursion_limit, limit)

    def test_empty_values(self):
        """
        Ensure bdecode and _decode handle empty values properly
        """
        decoder = bencode.Decoder()
        empty_bytes = ("empty bytes", bytes(), None)
        with self.subTest(msg=f"bdecode {empty_bytes[0]}"):
            self.assertEqual(decoder.decode(empty_bytes[1]), empty_bytes[2])

        with self.subTest(msg=f"_decode {empty_bytes[0]}"):
            with self.assertRaises(AttributeError):
                decoder._decode(empty_bytes[1]), empty_bytes[2]

        empty_buffer = ("empty buffer", BytesIO(empty_bytes[1]), None)
        empty_list = ("empty list", BytesIO(b"le"), [])
        empty_dict = ("empty dict", BytesIO(b"de"), OrderedDict())
        non_errors = [empty_buffer, empty_list, empty_dict]

        for case in non_errors:
            with self.subTest(msg=f"_decode {case[0]}"):
                self.assertEqual(decoder._decode(case[1]), case[2])

        empty_int = ("empty int", BytesIO(b"ie"), bencode.DecodeError)
        invalid_str = ("empty string", BytesIO(b"3:"), bencode.DecodeError)
        only_delim = ("only delim", BytesIO(b":"), bencode.DecodeError)
        errors = [empty_int, invalid_str, only_delim]

        for case in errors:
            with self.subTest(msg=f"_decode {case[0]}"):
                with self.assertRaises(case[2]):
                    decoder._decode(case[1])

    def test_bdecode_wrong_types(self):
        """
        Test that we can only decode a bytes-like object.
        Each type of object in bad_types must have len > 0 or bencode will return None
        """
        decoder = bencode.Decoder()
        bad_types = [[1, 2], "string", {"1": "a"}, (1, 2), {1, 2, 3}]
        for t in bad_types:
            with self.subTest(msg=f"bdecode {t}"):
                with self.assertRaises(bencode.DecodeError):
                    decoder.decode(t)

    def test__decode_imbalanced_delims(self):
        """
        Tests that _decode handles imbalanced delimiters
        imbalanced beginning delimiters are invalid
        imbalanced ending delimiters are ignored
        """
        decoder = bencode.Decoder()

        missing_start_delim = ("Missing start delim", BytesIO(b"3:vale"), b"val")
        ambiguous_end_delim = ("Ambiguous end delim", BytesIO(b"d3:val3:numee"), OrderedDict({b"val": b"num"}))
        list_extra_end_delim = ("List extra end delim", BytesIO(b"l3:oneeeee"), [b"one"])
        list_extra_end_delim_with_list = ("List extra end delim with list", BytesIO(b"l3:valeleeee"), [b"val"])
        dict_extra_end_delim = ("Dict extra end delim", BytesIO(b"d3:val3:valeeee"), OrderedDict({b"val": b"val"}))
        dict_extra_end_delim_with_list = (
            "Dict extra end delim with list", BytesIO(b"d3:num3:valeeelee"), OrderedDict({b"num": b"val"}))

        for k, v in locals().items():
            if k not in ["self", "decoder"]:
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEqual(decoder._decode(v[1]), v[2])

    def test__decode_recursion_limit(self):
        """
        Test that we get a BencodeRecursionError if we try to recursively decode an object that is too large
        """
        decoder = bencode.Decoder()
        decoder.recursion_limit = 5  # set to some low value so test runs quickly
        buffer = BytesIO(b"d3:val3:val3:val3:val3:val3:val3:val3:vale")
        with self.assertRaises(bencode.BencodeRecursionError):
            decoder._decode(buffer)

    def test__decode_consecutive_lists(self):
        """
        Tests that _decode can handle consecutive lists

        _decode will return a single list when consecutive lists are given
        even if one of those lists contains some data then empty lists
        if an empty list is encountered in a list with data after it, that data is not returned
        """
        decoder = bencode.Decoder()
        cons_lists = ("Consecutive lists", BytesIO(b"lelelelelele"), [])
        cons_lists_pop = ("Consecutive lists w/ populated", BytesIO(b"l3:vallee"), [b"val"])
        cons_lists_with_dict = ("Consecutive lists w/ dict value", BytesIO(b"lde3:vale"), [])
        cons_lists_pre_data = ("Consecutive lists before data", BytesIO(b"llelele3:vale"), [])

        for k, v in locals().items():
            if k not in ["self", "decoder"]:
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEqual(decoder._decode(v[1]), v[2])

    def test__decode_nested_list(self):
        """
        Tests that _decode can handle a nested list

        _decode will return a single list when empty lists are nested
        _decode will return nested lists if the innermost is populated, otherwise it will only recurse to the first
        list with data
        """
        decoder = bencode.Decoder()
        empty_nest = ("Empty nested lists", BytesIO(b"llleee"), [])
        pop_list = ("Populated nested list", BytesIO(b"ll3:valee"), [[b"val"]])
        nested_pop_list = ("Nested populated list", BytesIO(b"lll3:valeee"), [[[b"val"]]])
        pop_list_nested = ("Populated list w/ trailing nested empty lists", BytesIO(b"ll3:val"), [[b"val"]])

        for k, v in locals().items():
            if k not in ["self", "decoder"]:
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEqual(decoder._decode(v[1]), v[2])

    def test__decode_consecutive_dicts(self):
        """
        Tests that _decode can handle consecutive dicts
        _decode will return a single dict when consecutive dicts are given
        even if one of those dicts contains data then empty lists
        if an empty list is encountered in a dict with data after it, that data is not returned
        """
        decoder = bencode.Decoder()
        cons_dicts = ("Consecutive dicts", BytesIO(b"dedededede"), OrderedDict())
        populated_cons = ("Populated consecutive dicts", BytesIO(b"d3:val3:valede"), OrderedDict({b"val": b"val"}))
        populated_empty_key = ("Dict with empty key", BytesIO(b"dle3:val3:vale"), OrderedDict())

        for k, v in locals().items():
            if k not in ["self", "decoder"]:
                with self.subTest(msg=f"_decode {v[0]}"):
                    self.assertEqual(decoder._decode(v[1]), v[2])

    def test__decode_nested_dict(self):
        """
        Tests that _decode can handle a nested dict

        _decode will return a single dict when empty dicts are nested
        dictionaries can not be keys of dictionaries
        """
        empty = BytesIO(b"dddeee")
        res = bencode.Decoder()._decode(empty)
        self.assertEqual(res, OrderedDict())

    def test__decode_invalid_char(self):
        """
        Tests that _decode can handle an invalid character

        dicts can only contain string or integer keys and dict, string, list, integer values
        list can only contain string, integer, list, or
        """
        err = bencode.DecodeError
        decoder = bencode.Decoder()
        invalid_char = ("Invalid character", BytesIO(b"?"), err)
        invalid_key_dict = ("Invalid dict key", BytesIO(b"d?e"), err)
        empty_key_dict = ("Empty dict key", BytesIO(b"d3:e"), err)
        invalid_val_list = ("Invalid list value", BytesIO(b"l?e"), err)

        for k, v in locals().items():
            if k not in ["self", "err", "decoder"]:
                with self.subTest(msg=f"_decode {v[0]}"):
                    with self.assertRaises(v[2]):
                        decoder._decode(v[1])

    def test__decode_int(self):
        """
        Tests that the _decode_int function handles properly and improperly formatted bencoded integer data
        """
        decoder = bencode.Decoder()
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
                with self.assertRaises(bencode.DecodeError):
                    decoder._decode_int(BytesIO(b))

        for k, v in good_data.items():
            with self.subTest(k=k):
                self.assertEqual(decoder._decode_int(BytesIO(v)), k)

    def test__decode_str(self):
        """
        Tests that the _decode_str function handles properly and improperly formatted data
        """
        decoder = bencode.Decoder()
        bad_fmt = b"A:aaaaaaaa"
        wrong_delim = b"4-asdf"
        wrong_len_short = b"18:aaaaaaaaaaaaaaaa"
        right_len = b"18:aaaaaaaaaaaaaaaaaa"
        empty_str = b"0:"

        bad_data = [bad_fmt, wrong_delim, wrong_len_short]
        good_data = [right_len, empty_str]

        for b in bad_data:
            with self.subTest(b=b):
                with self.assertRaises(bencode.DecodeError):
                    decoder._decode_str(BytesIO(b))

        for b in good_data:
            with self.subTest(b=b):
                self.assertEqual(decoder._decode_str(BytesIO(b)), b[3:])

    def test__parse_num(self):
        """
        Tests _parse_num
        """
        decoder = bencode.Decoder()
        custom_delim = ("Custom delimiter", BytesIO(b"12%"), 12)
        with self.subTest(msg=f"_parse_num {custom_delim[0]}"):
            self.assertEqual(decoder._parse_num(custom_delim[1], delimiter=b"%"), 12)

        empty_val = ("Empty val", BytesIO())
        with self.subTest(msg=f"_parse_num {empty_val[0]}"):
            with self.assertRaises(bencode.DecodeError):
                decoder._parse_num(empty_val[1], 0)

        only_delim = ("Only delim", BytesIO(b":"))
        with self.subTest(msg=f"_parse_num {only_delim[0]}"):
            with self.assertRaises(bencode.DecodeError):
                decoder._parse_num(only_delim[1], 0)

        leading_zero = ("Leading zero", BytesIO(b"01:"))
        with self.subTest(msg=f"_parse_num {leading_zero[0]}"):
            with self.assertRaises(bencode.DecodeError):
                decoder._parse_num(leading_zero[1], 0)

        negative_zero = ("Negative zero", BytesIO(b"-0:"))
        with self.subTest(msg=f"_parse_num {negative_zero[0]}"):
            with self.assertRaises(bencode.DecodeError):
                decoder._parse_num(negative_zero[1], 0)


class Encoder(TestCase):
    """
    Test class for opalescence.Encoder
    """

    def test_empty_values(self):
        """
        Tests that the encoder handles receiving empty dicts.
        Returning none mirrors the behavior of passing empty binary data to the decoder
        """
        with self.subTest(msg="Empty dict"):
            self.assertEqual(bencode.Encoder().bencode(OrderedDict()), None)

    def test_wrong_types(self):
        """
        Tests that tne encoder rejects invalid types
        """
        bad_types = [{0, 1}, "string", None, True]
        encoder = bencode.Encoder()

        for t in bad_types:
            with self.subTest(msg=f"Bad type: {t}"):
                with self.assertRaises(bencode.EncodeError):
                    encoder._encode(t)

    def test__encode_empty_vals(self):
        """
        Tests that the encoder's _encode handles empty vals. The decoder is more strict about empty values in objects.
        """
        empty_dict = ("Empty dict", OrderedDict(), b"de")
        empty_list = ("Empty list", [], b"le")
        nested_empty_dicts = ("Nested empty dicts", OrderedDict({b"val": OrderedDict()}), b"d3:valdee")
        nested_empty_lists = ("Nested empty lists", [[]], b"llee")
        empty_string = ("Empty string", b"", b"0:")

        for k, v in locals().items():
            if k != "self":
                with self.subTest(msg=v[0]):
                    self.assertEqual(bencode.Encoder()._encode(v[1]), v[2])

    def test__encode(self):
        """
        Tests the main encoder method that recursively encodes an ordereddict
        """
        invalid_type = ("Invalid type in valid type", OrderedDict({b"val": {1, 2}}))
        with self.subTest(msg=invalid_type[0]):
            with self.assertRaises(bencode.EncodeError):
                bencode.Encoder()._encode(invalid_type[1])

        invalid_dict_key = ("Invalid dict key", OrderedDict({12: b"value"}))
        with self.subTest(msg=invalid_dict_key[0]):
            with self.assertRaises(bencode.EncodeError):
                bencode.Encoder()._encode(invalid_dict_key[1])

        a = OrderedDict()
        a[b"val"] = OrderedDict({b"hmm": [1, 2, 3, b"key"]})
        valid_dict = ("Valid dict", a, b"d3:vald3:hmmli1ei2ei3e3:keyeee")
        with self.subTest(msg=valid_dict[0]):
            self.assertEqual(bencode.Encoder()._encode(valid_dict[1]), valid_dict[2])

        valid_bytes = ("Valid bytes", b"these are valid bytes", b"21:these are valid bytes")
        with self.subTest(msg=valid_bytes[0]):
            self.assertEqual(bencode.Encoder()._encode(valid_bytes[1]), valid_bytes[2])

    def test__encode_int(self):
        """
        Tests the encoder's integer encoding
        """
        valid_int = [(12, b"i12e"), (0, b"i0e"), (-100, b"i-100e")]
        encoder = bencode.Encoder()
        for t in valid_int:
            with self.subTest(smg=f"Valid int {t[0]}"):
                self.assertEqual(encoder._encode_int(t[0]), t[1])

    def test__encode_bytestr(self):
        """
        Tests the encoder's bytestring encoding
        """
        valid_strings = [(b"value", b"5:value"), (b"", b"0:")]
        encoder = bencode.Encoder()

        for t in valid_strings:
            with self.subTest(msg=f"Valid string {t[0]}"):
                self.assertEqual(encoder._encode_bytestr(t[0]), t[1])
