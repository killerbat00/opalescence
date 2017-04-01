# -*- coding: utf-8 -*-

"""
Tests functionality related to bencoding and becoding bytes.
"""
import logging
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
                with self.assertLogs("Recursion limit should be greater than 0.", level=logging.ERROR):
                    for invalid_limit in [0, -1]:
                        bencode.Decoder(bytes(), recursion_limit=invalid_limit)

        with self.subTest(msg="No data."):
            with self.assertRaises(bencode.DecodeError):
                with self.assertLogs("No data received.", level=logging.ERROR):
                    bencode.Decoder(bytes())

        with self.subTest(msg="Invalid data types passed to Decoder."):
            with self.assertRaises(bencode.DecodeError):
                for invalid_type in [[1, 2], "string", {"1": "a"}, (1, 2), {1, 2, 3}]:
                    with self.assertLogs(f"Cannot decode data. Invalid type of {type(invalid_type)}.",
                                         level=logging.ERROR):
                        bencode.Decoder(invalid_type)

    def test_valid_creation(self):
        """
        Ensure __init__ works properly.
        """
        data = b"4:data"
        decoder = bencode.Decoder(data)
        self.assertIsInstance(decoder, bencode.Decoder)
        self.assertEqual(decoder._recursion_limit, 1000)
        self.assertEqual(decoder._current_iter, 0)
        self.assertEqual(decoder.data.read(), data)

    def test__set_data(self):
        """
        Ensure _set_data works properly.
        _set_data with invalid types is already tested in test_invalid_creation
        """
        old_data = b"8:old data"
        new_data = b"8:new data"
        decoder = bencode.Decoder(old_data)
        self.assertEqual(decoder.data.read(), old_data)
        decoder._set_data(new_data)
        self.assertEqual(decoder.data.read(), new_data)

    def test_decode(self):
        """
        Ensure bencode.Decoder.decode works properly
        """
        decoder = bencode.Decoder(b"e")
        with self.subTest(msg="Testing decode with nothing in the buffer."):
            decoder._set_data(b"")
            self.assertIsNone(decoder.decode())

        with self.subTest(msg="Testing decode with only an end delimiter."):
            self.assertIsNone(decoder.decode())

    def test__decode(self):
        """
        Ensure bencode.Decoder._decode works properly.
        """
        EOF = b"!"  # EOF marker used in the Decoder

        with self.subTest(msg="Testing _recursion_limit is reached."):
            with self.assertRaises(bencode.BencodeRecursionError):
                decoder = bencode.Decoder(b"l")
                decoder._current_iter = 5
                decoder._recursion_limit = 4
                decoder._decode()

        decoder = bencode.Decoder(b"l")

        with self.subTest(msg="Testing _decode with nothing in the buffer."):
            decoder.data.read(1)  # exhaust the buffer
            self.assertEqual(decoder._decode(), EOF)

        with self.subTest(msg="Testing _decode with only the end of a dictionary (or list, or int)."):
            decoder._set_data(bencode._Delims.DICT_END)  # empty dictionary also ends recursion
            self.assertEqual(decoder._decode(), EOF)

        with self.subTest(msg="Testing _decode with an empty dictionary."):
            decoder._set_data(b"de")
            self.assertEqual(decoder._decode(), OrderedDict())

        with self.subTest(msg="Testing _decode with an empty list."):
            decoder._set_data(b"le")
            self.assertEqual(decoder._decode(), [])

        with self.subTest(msg="Testing with an invalid bencoding key."):
            decoder._set_data(b"?")
            with self.assertRaises(bencode.DecodeError):
                with self.assertLogs(f"Unable to bdecode {b'?'}. Invalid bencoding key.", level=logging.ERROR):
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
                with self.assertLogs("Invalid dictionary key: 14. Dictionary keys must be bytestrings.",
                                     level=logging.ERROR):
                    decoder._set_data(data)
                    decoder._decode_dict()

        data = b"5:b key3:val5:a key3:vale"
        with self.subTest(msg="Unordered keys."):
            with self.assertRaises(bencode.DecodeError):
                with self.assertLogs(f"Invalid dictionary. Keys {[b'b key', b'a key']}.", level=logging.ERROR):
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

    def test__decode_str(self):
        """
        Ensures that Decoder._decode_str handles properly and improperly formatted data
        """
        data = b"13:nope"
        decoder = bencode.Decoder(data)
        with self.subTest(msg="Invalid string length."):
            with self.assertRaises(bencode.DecodeError):
                decoder.data.read(1)
                decoder._decode_str()

        data = b"3-val"
        with self.subTest(msg="Invalid delimiter."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder.data.read(1)
                decoder._decode_str()

        data = b"34:string with spaces and bytes \x00 \x12 \x24"
        with self.subTest(msg="Valid string."):
            decoder._set_data(data)
            decoder.data.read(1)
            self.assertEqual(decoder._decode_str(), data[3:])

    def test__parse_num(self):
        """
        Tests that the _parse_num handles integers correctly.
        """
        data = b"e"
        decoder = bencode.Decoder(data)
        with self.subTest(msg="Emtpy integer and onlydelim."):
            with self.assertRaises(bencode.DecodeError):
                decoder._parse_num(bencode._Delims.NUM_END)

        data = b"1^"
        with self.subTest(msg="Non-traditional delimiters."):
            decoder._set_data(data)
            self.assertEqual(decoder._parse_num(b"^"), 1)

        data = b"n12e"
        with self.subTest(msg="Not a digit or '-'."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._parse_num(bencode._Delims.NUM_END)

        data = b"01e"
        with self.subTest(msg="Leading zero."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._parse_num(bencode._Delims.NUM_END)

        data = b"-0e"
        with self.subTest(msg="Negative zero."):
            with self.assertRaises(bencode.DecodeError):
                decoder._set_data(data)
                decoder._parse_num(bencode._Delims.NUM_END)


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
