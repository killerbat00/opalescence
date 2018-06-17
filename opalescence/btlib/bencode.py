# -*- coding: utf-8 -*-

"""
Provides support for decoding a bencoded string into a python OrderedDict,
bencoding a decoded OrderedDict, and pretty printing said OrderedDict.
"""

import logging
from collections import OrderedDict
from io import BytesIO
from typing import Union, Optional, List

logger = logging.getLogger(__name__)

BencodingTypes = Union[OrderedDict, List, bytes, int]


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
    Delimiters used in the bencoding spec.
    """
    dict_start: bytes = b'd'
    end: bytes = b'e'
    list_start: bytes = b'l'
    num_start: bytes = b'i'
    divider: bytes = b':'
    digits: List[bytes] = [b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']
    eof: bytes = b"!"  # custom eof marker used to break out of empty containers


class Decoder:
    """
    Decodes a bencoded bytestring, returning its equivalent python
    representation.
    """

    def __init__(self, data: bytes, *, recursion_limit: int = 99999):
        """
        Creates a new Decoder object.

        :param data:            the bencoded bytes to decode
        :param recursion_limit: recursion limit for decoding methods
        :raises DecodeError:    if recursion limit is < 0 or no data received
        """
        if recursion_limit <= 0:
            logger.error(f"Cannot decode. Recursion limit should be greater "
                         f"than 0.")
            raise DecodeError

        if not data:
            logger.error(f"Cannot decode. No data received.")
            raise DecodeError

        self._recursion_limit: int = recursion_limit
        self._current_iter: int = 0
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
            logger.error(f"Expected bytes, received {type(data)}")
            logger.info(te, exc_info=True)
            raise DecodeError from te

    def decode(self) -> Optional[BencodingTypes]:
        """
        Decodes a bencoded bytestring, returning the data as python objects

        :return: decoded torrent info, or None if empty data received
        """
        try:
            decoded: BencodingTypes = self._decode()
            self._data.close()
        except (BencodeRecursionError, DecodeError) as de:
            logger.info(de, exc_info=True)
            raise DecodeError from de

        if decoded == BencodeDelimiters.eof:
            return
        return decoded

    def _decode(self) -> BencodingTypes:
        """
        Recursively decodes a BytesIO buffer of bencoded data

        :raises DecodeError:
        :raises BencodeRecursionError:
        :return: torrent info decoded into a python object
        """
        if self._current_iter > self._recursion_limit:
            logger.error(f"Recursion limit reached.")
            raise BencodeRecursionError
        else:
            self._current_iter += 1

        char: bytes = self._data.read(1)

        if not char:
            # eof is used to signal we've decoded as far as we can go
            return BencodeDelimiters.eof
        if char == BencodeDelimiters.end:
            # extra end delimiters are ignored -> d3:num3:valee = {"num", "val"}
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
            logger.error(f"Unable to bdecode {char}. Invalid bencoding key.")
            raise DecodeError

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
            key: BencodingTypes = self._decode()
            if key == BencodeDelimiters.eof:
                break
            if not isinstance(key, bytes):
                logger.error(f"Dictionary key must be bytes. Not {type(key)}")
                raise DecodeError

            val = self._decode()

            decoded_dict.setdefault(key, val)
            keys.append(key)

        if keys != sorted(keys):
            logger.error(f"Invalid dictionary. Keys {keys} not sorted.")
            raise DecodeError

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
        whitespace only strings are allowed if there is
        the proper number of whitespace characters to read.

        :raises DecodeError: if we are unable to read enough data for the string
        :return:             decoded string
        """
        # we've already consumed the string length, go back and get it
        self._data.seek(-1, 1)
        string_len: int = self._parse_num(BencodeDelimiters.divider)
        string_val: bytes = self._data.read(string_len)

        if len(string_val) != string_len:
            logger.error(f"Unable to read specified string {string_len}")
            raise DecodeError

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
            if char in BencodeDelimiters.digits + [b"-"]:
                parsed_num += char
            else:
                if char != delimiter:
                    logger.error(f"Invalid character while parsing int"
                                 f"{char}. Expected {delimiter}")
                    raise DecodeError
                break

        num_str: str = parsed_num.decode("UTF-8")

        if len(num_str) == 0:
            logger.error("Empty strings are not allowed for int keys.")
            raise DecodeError
        elif len(num_str) > 1 and (num_str[0] == '0' or num_str[:2] == '-0'):
            logger.error("Leading or negative zeros are not allowed for int "
                         "keys.")
            raise DecodeError

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
            logger.error("Cannot encode. No data received.")
            raise EncodeError

        self._data: BencodingTypes = data

    def encode(self) -> Optional[bytes]:
        """
        Bencodes a python object and returns the bencoded string.

        :raises EncodeError:
        :return: bencoded bytes or None if empty data received
        """
        if not self._data:
            return
        try:
            encoded_data: bytes = self._encode(self._data)
        except EncodeError as ee:
            logger.info(ee, exc_info=True)
            raise EncodeError from ee

        return encoded_data

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
            logger.error("Boolean values not supported.")
            raise EncodeError
        elif isinstance(obj, int):
            return self._encode_int(obj)
        else:
            logger.error(f"Unexpected object found {obj}")
            raise EncodeError

    def _encode_dict(self, obj: dict) -> bytes:
        """
        bencodes a python dictionary. Keys may only be bytestrings and they
        must be in ascending order according to their bytes.

        :param obj: dictionary to encode
        :raises EncodeError:
        :return: bencoded string of the decoded dictionary
        """
        contents: bytes = BencodeDelimiters.dict_start
        keys: List[bytes] = []
        for k, v in obj.items():
            if not isinstance(k, bytes):
                logger.error(f"Dictionary keys must be bytes. Not {type(k)}")
                raise EncodeError
            keys.append(k)
            key: bytes = self._encode_bytestr(k)
            contents += key
            contents += self._encode(v)
        contents += BencodeDelimiters.end
        if keys != sorted(keys):
            logger.error(f"Invalid dictionary. Keys {keys} are not sorted.")
            raise EncodeError
        return contents

    def _encode_list(self, obj: list) -> bytes:
        """
        bencodes a python list.

        :param obj: list to encode
        :return: bencoded string of the decoded list
        """
        contents: bytes = BencodeDelimiters.list_start
        for item in obj:
            val: Optional[BencodingTypes] = self._encode(item)
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
