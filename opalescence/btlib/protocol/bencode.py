# -*- coding: utf-8 -*-

"""
Provides support for decoding a bencoded string into a python OrderedDict,
bencoding a decoded OrderedDict, and pretty printing said OrderedDict.
"""

__all__ = ['Encode', 'Decode']

import logging
from collections import OrderedDict
from io import BytesIO
from typing import Union, Dict, AnyStr, Optional, List, SupportsInt

from .errors import *

BencodingTypes = Union[OrderedDict, Dict, List, AnyStr, SupportsInt]

logger = logging.getLogger(__name__)


class _BencodeRecursionError(Exception):
    """
    Raised when the recursion limit is reached.
    """


class _BencodeDelimiters:
    """
    Delimiters used in the bencoding spec.
    """
    DICT_START: bytes = b'd'
    END: bytes = b'e'
    LIST_START: bytes = b'l'
    NUM_START: bytes = b'i'
    SEPARATOR: bytes = b':'
    DIGITS: List[bytes] = [b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']
    EOF: bytes = b"!"  # eof marker used to break out of empty containers


def Decode(data: bytes) -> Optional[BencodingTypes]:
    """
    Public API for decoding bencoded bytes.
    :param data: bencoded bytes
    :raises DecodeError: on error
    :return: The decoded data transformed into corresponding Python types.
    """
    try:
        decoder = _Decoder(data)
        return decoder.decode()
    except DecodeError as exc:
        logger.error("%s" % exc)


def Encode(data: BencodingTypes) -> bytes:
    """
    Public API for bencoding python types to bytes.
    :param data: encoded data
    :raises DecodeError: on error
    :return: The decoded data transformed into corresponding Python types.
    """
    try:
        encoder = Encoder(data)
        return encoder.encode()
    except EncodeError as exc:
        logger.error("%s" % exc)


class _Decoder:
    """
    Decodes a bencoded bytestring, returning its equivalent python
    representation.
    """

    def __init__(self, data: bytes, *, recursion_limit: int = 99999):
        """
        Creates a new _Decoder object.

        :param data:            the bencoded bytes to decode
        :param recursion_limit: recursion limit for decoding methods
        :raises DecodeError:    if recursion limit is < 0 or no data received
        """
        if recursion_limit <= 0:
            raise DecodeError(f"Cannot decode. Recursion limit should be greater than 0.")

        if not data:
            raise DecodeError(f"Cannot decode. No data received.")

        self._recursion_limit: int = recursion_limit
        self._current_iter: int = 0
        self._data: Optional[BytesIO] = None
        self._set_data(data)

    def _set_data(self, data: bytes) -> None:
        """
        Sets the data used by the decoder.
        Warning: _set_data does not check if the data passed in as an argument
        exists.
        calling decode() after setting no data will return None.

        :param data: bytes of data to decode
        """
        try:
            self._data: BytesIO = BytesIO(data)
            self._current_iter = 0
        except TypeError as te:
            raise DecodeError(f"Expected bytes, received {type(data)}") from te

    def decode(self) -> Optional[BencodingTypes]:
        """
        Decodes a bencoded bytestring, returning the data as python objects

        :raises: DecodeError
        :return: decoded torrent info, or None if empty data received
        """
        try:
            decoded: BencodingTypes = self._decode()
            self._data.close()
        except Exception:
            raise DecodeError

        if decoded == _BencodeDelimiters.EOF:
            return
        return decoded

    def _decode(self) -> BencodingTypes:
        """
        Recursively decodes a BytesIO buffer of bencoded data

        :raises DecodeError:
        :raises _BencodeRecursionError:
        :return: torrent info decoded into a python object
        """
        if self._current_iter > self._recursion_limit:
            raise _BencodeRecursionError(f"Recursion limit reached.")
        else:
            self._current_iter += 1

        char: bytes = self._data.read(1)

        if not char:
            # eof is used to signal we've decoded as far as we can go
            return _BencodeDelimiters.EOF
        if char == _BencodeDelimiters.END:
            # extra end delimiters are ignored -> d3:num3:valee = {"num", "val"}
            return _BencodeDelimiters.EOF
        elif char == _BencodeDelimiters.NUM_START:
            return self._decode_int()
        elif char in _BencodeDelimiters.DIGITS:
            return self._decode_bytestr()
        elif char == _BencodeDelimiters.DICT_START:
            return self._decode_dict()
        elif char == _BencodeDelimiters.LIST_START:
            return self._decode_list()
        else:
            raise DecodeError(f"Unable to bdecode {char}. Invalid bencoding key.")

    def _decode_dict(self) -> OrderedDict:
        """
        Decodes a bencoded dictionary into an OrderedDict
        only bytestrings are allowed as keys for bencoded dictionaries
        dictionary keys must be sorted according to their raw bytes

        :raises DecodeError:
        :return: decoded dictionary as OrderedDict
        """
        decoded_dict: OrderedDict = OrderedDict()
        keys: List[bytes] = []

        while True:
            key: bytes = self._decode()
            if not isinstance(key, bytes):
                raise DecodeError(f"Dictionary key must be bytes. Not {type(key)}")
            if key == _BencodeDelimiters.EOF:
                break
            val = self._decode()

            decoded_dict.setdefault(key.decode("UTF-8"), val)
            keys.append(key)

        if keys != sorted(keys):
            raise DecodeError(f"Invalid dictionary. Keys {keys} not sorted.")

        return decoded_dict

    def _decode_list(self) -> List:
        """
        Decodes a bencoded list into a python list
        lists can contain any other bencoded types:
            (bytestring, integer, list, dictionary)

        :return: list of decoded data
        """
        decoded_list: List[BencodingTypes] = []
        while True:
            item: BencodingTypes = self._decode()
            if item == _BencodeDelimiters.EOF:
                break
            decoded_list.append(item)
        return decoded_list

    def _decode_int(self) -> int:
        """
        decodes a bencoded integer from the BytesIO buffer.

        :return: decoded integer
        """
        return self._parse_num(_BencodeDelimiters.END)

    def _decode_bytestr(self) -> bytes:
        """
        decodes a bencoded string from the BytesIO buffer.
        whitespace only strings are allowed if there is
        the proper number of whitespace characters to read.

        :raises DecodeError: if we are unable to read enough data for the string
        :return:             decoded string
        """
        # we've already consumed the string length, go back and get it
        self._data.seek(-1, 1)
        string_len: int = self._parse_num(_BencodeDelimiters.SEPARATOR)
        string_val: bytes = self._data.read(string_len)

        if len(string_val) != string_len:
            raise DecodeError(f"Unable to read specified string {string_len}")

        return string_val

    def _parse_num(self, delimiter: bytes) -> int:
        """
        parses an bencoded integer up to specified delimiter from the buffer.

        :param delimiter:    delimiter do indicate the end of the number
        :raises DecodeError: when an invalid character occurs
        :return:             decoded number
        """
        parsed_num: bytes = bytes()
        while True:
            char: bytes = self._data.read(1)
            # allow negative integers
            if char in _BencodeDelimiters.DIGITS + [b"-"]:
                parsed_num += char
            else:
                if char != delimiter:
                    raise DecodeError(f"Invalid character while parsing int {char}."
                                      f"Expected {delimiter}")
                break

        num_str: str = parsed_num.decode("UTF-8")

        if len(num_str) == 0:
            raise DecodeError("Empty strings are not allowed for int keys.")
        elif len(num_str) > 1 and (num_str[0] == '0' or num_str[:2] == '-0'):
            raise DecodeError("Leading or negative zeros are not allowed for int keys.")

        return int(num_str)


class Encoder:
    """
    Encodes a python object and returns the bencoded bytes
    """

    def __init__(self, data: BencodingTypes):
        """
        Creates an Encoder instance with the specified data.

        :param data:         dict, list, byte, or int data to encode
        :raises EncodeError: when null data received
        """
        if not data:
            raise EncodeError("Cannot encode. No data received.")

        self._data: BencodingTypes = data

    def encode(self) -> Optional[bytes]:
        """
        Bencodes a python object and returns the bencoded string.

        :raises EncodeError:
        :return: bencoded bytes or None if empty data received
        """
        return self._encode(self._data)

    def _encode(self, obj: BencodingTypes) -> bytes:
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
            raise EncodeError(f"Unexpected object found {type(obj)}:{obj}")
        elif isinstance(obj, int):
            return self._encode_int(obj)
        else:
            raise EncodeError(f"Unexpected object found {type(obj)}:{obj}")

    def _encode_dict(self, obj: dict) -> bytes:
        """
        bencodes a python dictionary. Keys may only be bytestrings and they
        must be in ascending order according to their bytes.

        :param obj: dictionary to encode
        :raises EncodeError:
        :return: bencoded string of the decoded dictionary
        """
        contents: bytes = _BencodeDelimiters.DICT_START
        keys: List[bytes] = []
        for k, v in obj.items():
            if isinstance(k, str):
                k = k.encode("UTF-8")
            else:
                raise EncodeError(f"Dictionary keys must be bytes. Not {type(k)}")
            keys.append(k)
            key = self._encode_bytestr(k)
            contents += key
            contents += self._encode(v)
        contents += _BencodeDelimiters.END
        if keys != sorted(keys):
            raise EncodeError(f"Invalid dictionary. Keys {keys} are not sorted.")
        return contents

    def _encode_list(self, obj: list) -> bytes:
        """
        bencodes a python list.

        :param obj: list to encode
        :return: bencoded string of the decoded list
        """
        contents: bytes = _BencodeDelimiters.LIST_START
        for item in obj:
            val: Optional[BencodingTypes] = self._encode(item)
            if val:
                contents += val
        contents += _BencodeDelimiters.END
        return contents

    @staticmethod
    def _encode_int(int_obj: int) -> bytes:
        """
        bencodes an integer.

        :param int_obj: integer to bencode
        :return:        bencoded string of the specified integer
        """
        ret = bytes()
        ret += _BencodeDelimiters.NUM_START
        ret += str(int_obj).encode("UTF-8")
        ret += _BencodeDelimiters.END
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
        ret += _BencodeDelimiters.SEPARATOR
        ret += string_obj
        return ret
