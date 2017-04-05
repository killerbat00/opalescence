# -*- coding: utf-8 -*-

"""
Provides support for decoding a bencoded string into a python OrderedDict,
bencoding a decoded OrderedDict, and pretty printing said OrderedDict.

public classes:
    Encoder()
    Decoder()

public Exceptions:
    BencodeRecursionError()
    DecodeError()
    EncodeError()
"""
import logging
from collections import OrderedDict
from io import BytesIO
from typing import Union

from . import log_and_raise

logger = logging.getLogger(__name__)


class BencodeRecursionError(Exception):
    """
    Raised when the recursion limit is reached.
    """


class DecodeError(Exception):
    """
    Raised when there's an issue decoding a bencoded object.
    """


class EncodeError(Exception):
    """
    Raised when there's an issue bencoding an object.
    """


class BencodeDelimiters:
    """
    Delimiters used for bencoding
    """
    dict_start = b'd'
    end = b'e'
    list_start = b'l'
    num_start = b'i'
    divider = b':'
    digits = [b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']
    eof = b"!"


class Decoder:
    """
    Decodes a bencoded bytestring, returning it's equivalent python object representation.
    """

    def __init__(self, data: bytes, recursion_limit: int = 99999):
        """
        Creates a new Decoder object.

        :param data:            the bencoded bytes to decode
        :param recursion_limit: the number of times we'll recursively call into the decoding methods
        :raises DecodeError:    if recursion limit is < 0 or no data received
        """
        if recursion_limit <= 0:
            log_and_raise("Recursion limit should be greater than 0.", logger, DecodeError)

        if not data:
            log_and_raise("No data received.", logger, DecodeError)

        self._recursion_limit = recursion_limit
        self._current_iter = 0
        self._set_data(data)

    def _set_data(self, data: bytes) -> None:
        """
        Sets the data used by the decoder.
        Warning: _set_data does not check if the data passed in as an argument exists.
        calling decode() after setting no data will return None.

        :param data: bytes of data to decode
        """
        try:
            self.data = BytesIO(data)
            self._current_iter = 0
        except TypeError as te:
            log_and_raise(f"Cannot set data. Invalid type of {type(data)}", logger, DecodeError, te)

    def decode(self) -> Union[OrderedDict, list, bytes, int, None]:
        """
        Decodes a bencoded bytestring, returning the data as python objects

        :return: decoded torrent info, or None if empty data received
        """
        decoded = self._decode()
        if decoded == BencodeDelimiters.eof:
            return
        return decoded

    def _decode(self) -> Union[OrderedDict, list, bytes, int]:
        """
        Recursively decodes a BytesIO buffer of bencoded data

        :raises DecodeError:
        :raises BencodeRecursionError:
        :return: torrent info decoded into a python object
        """
        if self._current_iter > self._recursion_limit:
            log_and_raise("Recursion limit reached.", logger, BencodeRecursionError)
        else:
            self._current_iter += 1

        char = self.data.read(1)

        if not char:
            # ends the recursive madness. eof is used to signal we've decoded as far as we can go
            return BencodeDelimiters.eof
        if char == BencodeDelimiters.end:
            # extraneous end delimiters are ignored -> d3:num3:valee = {"num", "val"}
            return BencodeDelimiters.eof
        elif char == BencodeDelimiters.num_start:
            return self._decode_int()
        elif char in BencodeDelimiters.digits:
            return self._decode_bytestr()
        elif char == BencodeDelimiters.dict_start:
            return self._decode_dict()
        elif char == BencodeDelimiters.list_start:
            return self._decode_list()
        else:
            log_and_raise(f"Unable to bdecode {char}. Invalid bencoding key.", logger, DecodeError)

    def _decode_dict(self) -> OrderedDict:
        """
        Decodes a bencoded dictionary into an OrderedDict
        only bytestrings are allowed as keys for bencoded dictionaries
        dictionary keys must be sorted according to their raw bytes

        :raises DecodeError:
        :return: decoded dictionary as OrderedDict
        """
        decoded_dict = OrderedDict()
        keys = []

        while True:
            key = self._decode()
            if key == BencodeDelimiters.eof:
                break
            if not isinstance(key, bytes):
                log_and_raise(f"Dictionary key must be bytes. Not {type(key)}.", logger, DecodeError)
            val = self._decode()

            decoded_dict.setdefault(key, val)
            keys.append(key)

        if keys != sorted(keys):
            log_and_raise(f"Invalid dictionary. Keys {keys} are not sorted.", logger, DecodeError)

        return decoded_dict

    def _decode_list(self) -> list:
        """
        Decodes a bencoded list into a python list
        lists can contain any other bencoded types (bytestring, integer, list, dictionary)

        :return: list of decoded data
        """
        decoded_list = []
        while True:
            item = self._decode()
            if item == BencodeDelimiters.eof:
                break
            decoded_list.append(item)
        return decoded_list

    def _decode_int(self) -> int:
        """
        decodes a bencoded integer from the BytesIO buffer.

        :return: decoded integer
        """
        return self._parse_num(BencodeDelimiters.end)

    def _decode_bytestr(self) -> bytes:
        """
        decodes a bencoded string from the BytesIO buffer.
        whitespace only strings are allowed if there is the proper number of whitespace characters to read.

        :raises DecodeError: if we are unable to read enough data for the string
        :return:             decoded string
        """
        # we've already consumed the byte that will start the string length, go back and get it
        self.data.seek(-1, 1)
        string_len = self._parse_num(BencodeDelimiters.divider)
        string_val = self.data.read(string_len)

        if len(string_val) != string_len:
            log_and_raise(f"Unable to read specified string length {string_len}", logger, DecodeError)

        return string_val

    def _parse_num(self, delimiter: bytes) -> int:
        """
        parses an bencoded integer up to specified delimiter from the BytesIO buffer.

        :param delimiter:    delimiter do indicate the end of the number
        :raises DecodeError: when an invalid character occurs
        :return:             decoded number
        """
        parsed_num = bytes()
        while True:
            char = self.data.read(1)
            if char in BencodeDelimiters.digits + [b"-"]:  # allow negative integers
                parsed_num += char
            else:
                if char != delimiter:
                    log_and_raise(f"Invalid character while parsing int {char}. Expected {delimiter}", logger,
                                  DecodeError)
                break

        num_str = parsed_num.decode("UTF-8")

        if len(num_str) == 0:
            log_and_raise("Empty strings are not allowed for int keys.", logger, DecodeError)
        elif len(num_str) > 1 and (num_str[0] == '0' or num_str[:2] == '-0'):
            log_and_raise("Leading or negative zeros are not allowed for int keys.", logger, DecodeError)

        return int(num_str)


class Encoder:
    """
    Encodes a python object and returns the bencoded bytes
    """

    def __init__(self, data: Union[dict, list, bytes, int]):
        """
        Creates an Encoder instance with the specified data.

        :param data:         dict, list, byte, or int data to encode
        :raises EncodeError: when null data received
        """
        if not data:
            log_and_raise("No data received.", logger, EncodeError)

        self._set_data(data)

    def _set_data(self, data: Union[dict, list, bytes, int]) -> None:
        """
        Sets the data being used by the encoder
        Warning: the length or existence of data is not checked here

        :param data: python object to set as data
        """
        self.data = data

    def encode(self) -> Union[bytes, None]:
        """
        Bencodes a python object and returns the bencoded string.

        :raises EncodeError:
        :return: bencoded bytes or None if empty data received
        """
        if not self.data:
            return

        return self._encode(self.data)

    def _encode(self, obj: Union[dict, list, bytes, int]) -> bytes:
        """
        Recursively bencodes a python object

        :param obj: object to decode
        :raises EncodeError:
        :return:    bencoded string
        """
        if isinstance(obj, dict):
            return self._encode_dict(obj)
        elif isinstance(obj, list):
            return self._encode_list(obj)
        elif isinstance(obj, bytes):
            return self._encode_bytestr(obj)
        elif isinstance(obj, bool):
            log_and_raise("Boolean values not supported.", logger, EncodeError)
        elif isinstance(obj, int):
            return self._encode_int(obj)
        else:
            log_and_raise(f"Unexpected object found {obj}", logger, EncodeError)

    def _encode_dict(self, obj: dict) -> bytes:
        """
        bencodes a python dictionary.
        Keys may only be bytestrings and they must be in ascending order according to their bytes.

        :param obj: dictionary to encode
        :raises EncodeError:
        :return: bencoded string of the decoded dictionary
        """
        contents = BencodeDelimiters.dict_start
        keys = []
        for k, v in obj.items():
            if not isinstance(k, bytes):
                log_and_raise(f"Dictionary keys must be bytes. Not {type(k)}", logger, EncodeError)
            keys.append(k)
            key = self._encode_bytestr(k)
            contents += key
            contents += self._encode(v)
        contents += BencodeDelimiters.end
        if keys != sorted(keys):
            log_and_raise(f"Invalid dictionary. Keys {keys} not sorted.", logger, EncodeError)
        return contents

    def _encode_list(self, obj: list) -> bytes:
        """
        bencodes a python list.

        :param obj: list to encode
        :return: bencoded string of the decoded list
        """
        contents = BencodeDelimiters.list_start
        for item in obj:
            val = self._encode(item)
            if val:
                contents += val
        contents += BencodeDelimiters.end
        return contents

    @staticmethod
    def _encode_int(int_obj: int) -> bytes:
        """
        bencodes an integer.

        :param int_obj: integer to bencode
        :return:        bencoded string of the specified integer
        """
        ret = bytes()
        ret += BencodeDelimiters.num_start
        ret += str(int_obj).encode("UTF-8")
        ret += BencodeDelimiters.end
        return ret

    @staticmethod
    def _encode_bytestr(string_obj: bytes) -> bytes:
        """
        bencode a string of bytes

        :param string_obj: string to bencode
        :return:           bencoded string of the specified string
        """
        ret = bytes()
        ret += str(len(string_obj)).encode("UTF-8")
        ret += BencodeDelimiters.divider
        ret += string_obj
        return ret
