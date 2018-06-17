# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.
"""
from collections import OrderedDict
from unittest import TestCase

from tests.context import bencode


class TestDecoder(TestCase):
    """
    Test class for opalescence.Decoder
    """

    def test_invalid_creation(self):
        """
        Ensure __init__ rejects invalid arguments.
        """
        with self.subTest(msg="Invalid recursion limit."):
            with self.assertRaises(bencode.DecodeError):
                for invalid_limit in [0, -1]:
                    bencode.Decoder(bytes(), recursion_limit=invalid_limit)

        with self.subTest(msg="No data."):
            with self.assertRaises(bencode.DecodeError):
                bencode.Decoder(bytes())

        with self.subTest(msg="Invalid data types passed to Decoder."):
            with self.assertRaises(bencode.DecodeError):
                for invalid_type in [[1, 2], "string", {"1": "a"}, (1, 2), {1, 2, 3}]:
                    bencode.Decoder(invalid_type)

    def test_valid_creation(self):
        """
        Ensure __init__ works properly.
        """
        data = b"4:data"
        decoder = bencode.Decoder(data)
        self.assertIsInstance(decoder, bencode.Decoder)
        self.assertEqual(decoder._recursion_limit, 99999)
        self.assertEqual(decoder._current_iter, 0)
        self.assertEqual(decoder._data.read(), data)

    def test__set_data(self):
        """
        Ensure _set_data works properly.
        _set_data with invalid types is already tested in test_invalid_creation
        """
        old_data = b"8:old data"
        new_data = b"8:new data"
        empty_data = b""
        decoder = bencode.Decoder(old_data)
        self.assertEqual(decoder._data.read(), old_data)
        decoder._set_data(new_data)
        self.assertEqual(decoder._data.read(), new_data)
        decoder._set_data(empty_data)
        self.assertEqual(decoder._data.read(), empty_data)
        decoder._set_data(empty_data)
        self.assertIsNone(decoder.decode())

    def test__decode(self):
        """
        Ensure bencode.Decoder._decode works properly.
        """
        eof = b"!"  # eof marker used in the Decoder

        with self.subTest(msg="Testing _recursion_limit is reached."):
            with self.assertRaises(bencode.BencodeRecursionError):
                decoder = bencode.Decoder(b"l")
                decoder._current_iter = 5
                decoder._recursion_limit = 4
                decoder._decode()

        decoder = bencode.Decoder(b"l")

        with self.subTest(msg="Testing _decode with nothing in the buffer."):
            decoder._data.read(1)  # exhaust the buffer
            self.assertEqual(decoder._decode(), eof)

        with self.subTest(msg="Testing _decode with only the end of a dictionary (or list, or int)."):
            decoder._set_data(bencode.BencodeDelimiters.end)  # empty dictionary also ends recursion
            self.assertEqual(decoder._decode(), eof)

        with self.subTest(msg="Testing _decode with an empty dictionary."):
            decoder._set_data(b"de")
            self.assertEqual(decoder._decode(), OrderedDict())

        with self.subTest(msg="Testing _decode with an empty list."):
            decoder._set_data(b"le")
            self.assertEqual(decoder._decode(), [])

        with self.subTest(msg="Testing with an invalid bencoding key."):
            decoder._set_data(b"?")
            with self.assertRaises(bencode.DecodeError):
                decoder._decode()

    def test__decode_dict(self):
        """
        Tests that Decoder._decode_dict functions properly

        we leave the dictionary start delimiter b'd' off as we call into _decode_dict directly.
        """
        data = b"e"
        decoder = bencode.Decoder(data)
        with self.subTest(msg="Decode with no key in the Decoder."):
            self.assertEqual(decoder._decode_dict(), OrderedDict())

        data = b"i14e4:datae"
        with self.subTest(msg="Invalid dictionary key type."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._decode_dict()

        data = b"5:b key3:val5:a key3:vale"
        with self.subTest(msg="Unordered keys."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._decode_dict()

        data = b"3:key3:vale"
        with self.subTest(msg="Valid dictionary."):
            decoder._set_data(data)
            self.assertEqual(decoder._decode_dict(), OrderedDict({b"key": b"val"}))

        data = b"3:key3:valeee"
        with self.subTest(msg="Extra end delimiters."):
            decoder._set_data(data)
            self.assertEqual(decoder._decode_dict(), OrderedDict({b"key": b"val"}))

    def test__decode_list(self):
        """
        Tests that Decoder._decode_list functions properly

        we leave the list start delimiter b'l' off as we call into _decode_list directly.
        """
        data = b"e"  # le
        decoder = bencode.Decoder(data)
        with self.subTest(msg="Empty list."):
            self.assertEqual(decoder._decode_list(), [])

        data = b"lee"  # llee
        with self.subTest(msg="Nested empty lists."):
            decoder._set_data(data)
            self.assertEqual(decoder._decode_list(), [[]])

        data = b"l3:valee"  # ll3:valee
        with self.subTest(msg="Populated inner list."):
            decoder._set_data(data)
            self.assertEqual(decoder._decode_list(), [[b"val"]])

        data = b"3:vall3:val3:val3:valel3:valedee"  # 3:vall3:val3:val3:valel3:valedee
        with self.subTest(msg="Populated with many types."):
            decoder._set_data(data)
            self.assertEqual(decoder._decode_list(),
                             [b"val", [b"val", b"val", b"val"], [b"val"], OrderedDict()])

        data = b"3:valeee"
        with self.subTest(msg="Extra end delimiters."):
            decoder._set_data(data)
            self.assertEqual(bencode.Decoder(data)._decode_list(), [b"val"])

        data = b"?e"
        with self.subTest(msg="Invalid list item."):
            decoder._set_data(data)
            with self.assertRaises(bencode.DecodeError):
                bencode.Decoder(data)._decode_list()

    def test__decode_bytestr(self):
        """
        Ensures that Decoder._decode_bytestr handles properly and improperly formatted data
        """
        data = b"13:nope"
        decoder = bencode.Decoder(data)
        with self.subTest(msg="Invalid string length."):
            with self.assertRaises(bencode.DecodeError):
                decoder._data.read(1)
                decoder._decode_bytestr()

        data = b"3-val"
        with self.subTest(msg="Invalid delimiter."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._data.read(1)
                decoder._decode_bytestr()

        data = b"34:string with spaces and bytes \x00 \x12 \x24"
        with self.subTest(msg="Valid string."):
            decoder._set_data(data)
            decoder._data.read(1)
            self.assertEqual(decoder._decode_bytestr(), data[3:])

    def test__parse_num(self):
        """
        Tests that the _parse_num handles integers correctly.
        """
        data = b"e"
        decoder = bencode.Decoder(data)
        with self.subTest(msg="Emtpy integer and onlydelim."):
            with self.assertRaises(bencode.DecodeError):
                decoder._parse_num(bencode.BencodeDelimiters.end)

        data = b"1^"
        with self.subTest(msg="Non-traditional delimiters."):
            decoder._set_data(data)
            self.assertEqual(decoder._parse_num(b"^"), 1)

        data = b"n12e"
        with self.subTest(msg="Not a digit or '-'."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._parse_num(bencode.BencodeDelimiters.end)

        data = b"01e"
        with self.subTest(msg="Leading zero."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._parse_num(bencode.BencodeDelimiters.end)

        data = b"-0e"
        with self.subTest(msg="Negative zero."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._parse_num(bencode.BencodeDelimiters.end)


class TestEncoder(TestCase):
    """
    Test class for opalescence.Encoder
    """

    def test_invalid_creation(self):
        """
        Test that we cannot create an encoder object from invalid data.
        """
        for bad_data in [None, [], bytes(), OrderedDict(), 0]:
            with self.subTest(msg=f"No/empty data {bad_data}."):
                with self.assertRaises(bencode.EncodeError):
                    bencode.Encoder(bad_data)

    def test_valid_creation(self):
        """
        Test that we can create an encoder object from valid data.
        """
        for good_data in [[1, 2, 3], 1, b"string", b"12", {b"key": 3}]:
            with self.subTest(msg=f"Good data {good_data}."):
                self.assertIsInstance(bencode.Encoder(good_data), bencode.Encoder)

    def test__encode(self):
        """
        Tests that _encode functions properly.
        """
        empty_vals = {b"de": dict(), b"le": list(), b"0:": bytes()}
        encoder = bencode.Encoder([1, 2, 3])  # bogus data
        for k, v in empty_vals.items():
            with self.subTest(msg=f"Empty value {v}."):
                self.assertEqual(encoder._encode(v), k)

        invalid_vals = [True, set(), TestCase]
        for v in invalid_vals:
            with self.subTest(msg=f"Invalid value {v}."):
                with self.assertRaises(bencode.EncodeError):
                    encoder._encode(v)

    def test__encode_dict(self):
        """
        Tests the implementation of dictionary bencoding.
        """
        encoder = bencode.Encoder([1, 2, 3])  # bogus data
        with self.subTest(msg="Invalid dict key."):
            with self.assertRaises(bencode.EncodeError):
                data = OrderedDict({1: b"val"})
                encoder._encode_dict(data)

        with self.subTest(msg="Unsorted keys."):
            with self.assertRaises(bencode.EncodeError):
                data = OrderedDict({b"b": b"val",
                                    b"a": b"val"})
                encoder._encode_dict(data)

        with self.subTest(msg="Valid dictionary."):
            data = OrderedDict({b"a": OrderedDict({b"b": [1, 2, 3]})})
            self.assertEqual(encoder._encode_dict(data), b"d1:ad1:bli1ei2ei3eeee")

    def test__encode_list(self):
        """
        Tests the implementation of list bencoding.
        """
        valid_lists = [([1, 2, 3], b"li1ei2ei3ee"),
                       ([[1], [], [1]], b"lli1eeleli1eee"),
                       ([b"val", OrderedDict({b"key": b"val"}), [[]]], b"l3:vald3:key3:valelleee")]
        encoder = bencode.Encoder([1, 2, 3])  # bogus data
        for case in valid_lists:
            with self.subTest(msg=f"Valid list {case[0]}"):
                self.assertEqual(encoder._encode_list(case[0]), case[1])

    def test__encode_int(self):
        """
        Tests the encoder's integer encoding
        """
        valid_int = [(12, b"i12e"), (0, b"i0e"), (-100, b"i-100e")]
        encoder = bencode.Encoder([1, 2, 3])  # bogus data
        for t in valid_int:
            with self.subTest(smg=f"Valid int {t[0]}"):
                self.assertEqual(encoder._encode_int(t[0]), t[1])

    def test__encode_bytestr(self):
        """
        Tests the encoder's bytestring encoding
        """
        valid_strings = [(b"value", b"5:value"), (b"", b"0:")]
        encoder = bencode.Encoder([1, 2, 3])  # bogus data

        for t in valid_strings:
            with self.subTest(msg=f"Valid string {t[0]}"):
                self.assertEqual(encoder._encode_bytestr(t[0]), t[1])
