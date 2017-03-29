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

logger = logging.getLogger('opalescence.' + __name__)


class BencodeRecursionError(Exception):
    """
    Raised when the RECURSION_LIMIT is reached
    """
    pass


class DecodeError(Exception):
    """
    Raised when there's an issue decoding a bencoded object.
    """
    pass


class EncodeError(Exception):
    """
    Raised when there's an issue bencoding an object.
    """
    pass


class _Delims:
    """
    Delimiters used for bencoding
    """
    DICT_START = b'd'
    DICT_END = b'e'
    LIST_START = b'l'
    LIST_END = DICT_END
    NUM_START = b'i'
    NUM_END = DICT_END
    DIVIDER = b':'
    DIGITS = [b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']
    VALID_CHARS = [DICT_START, DICT_END, LIST_START, NUM_START, DIVIDER] + DIGITS


class Decoder:
    """
    Decodes a benoded bytestring, returning an OrderedDict.
    """

    def __init__(self, recursion_limit: int = 1000):
        if recursion_limit <= 0:
            raise DecodeError("Recursion limit should be greater than 0. Preferably 1000 or above (roughly).")

        self.recursion_limit = recursion_limit
        self.current_iter = 0

    def decode(self, data: bytes) -> Union[OrderedDict, None]:
        """
        Decodes a bencoded bytestring, returning an OrderedDict.

        :param data: bencoed bytes of data
        :return:     decoded torrent info as an OrderedDict
                     None if empty bytes received
        :raises:     DecodeError
        """
        logger.debug("bdecoding bytes")

        if len(data) == 0:
            return None

        try:
            data = BytesIO(data)
        except TypeError as te:
            logger.error(f"Cannot decode, invalid type of {type(data)}")
            raise DecodeError from te
        else:
            return self._decode(data)

    def _decode(self, data: BytesIO) -> Union[OrderedDict, list, bytes, int]:
        """
        Recursively decodes a BytesIO buffer of bencoded data

        :param data: BytesIO of bencoded binary data
        :return:     torrent info decoded into a python object
        :raises:     DecodeError, BencodeRecursionError
        """
        if self.current_iter > self.recursion_limit:
            logger.error(f"Recursion limit of {self.recursion_limit} reached.")
            raise BencodeRecursionError
        else:
            self.current_iter += 1

        char = data.read(1)

        if not char:
            return
        if char == _Delims.DICT_END:
            # mismatched end delimiters are ignored -> d3:num3:valee = {"num", "val"}
            return
        elif char == _Delims.NUM_START:
            return self._decode_int(data)
        elif char in _Delims.DIGITS:
            return self._decode_str(data)
        elif char == _Delims.DICT_START:
            decoded_dict = OrderedDict()
            keys = []
            while True:
                key = self._decode(data)
                if not key:
                    break
                val = self._decode(data)
                keys.append(key)
                try:
                    decoded_dict.setdefault(key, val)
                except TypeError:
                    logger.error("Tried to set an ordered dictionary as a key. Dictionaries cannot be keys")
                    raise DecodeError
            if keys != sorted(keys):
                logger.error("Unable to decode bencoded dictionary. Keys are not sorted.")
                raise DecodeError
            return decoded_dict
        elif char == _Delims.LIST_START:
            decoded_list = []
            while True:
                item = self._decode(data)
                if not item:
                    break
                decoded_list.append(item)
            return decoded_list
        else:
            logger.error(f"Unable to bdecode stream. {char} is invalid bencoded type of value.")
            raise DecodeError

    def _decode_int(self, data: BytesIO) -> int:
        """
        decodes a bencoded integer from a BytesIO buffer.

        :param data: BytesIO stream of bencoded binary data
        :return:     decoded integer
        :raises:     DecodeError
        """
        data.seek(-1, 1)
        char = data.read(1)
        if char != _Delims.NUM_START:
            logger.error(
                f"Error while parsing integer. Found {char}, expected {_Delims.NUM_START}.")
            raise DecodeError
        return self._parse_num(data, delimiter=_Delims.NUM_END)

    def _decode_str(self, data: BytesIO) -> bytes:
        """
        decodes a bencoded string from a BytesIO buffer.
        empty strings are allowed if there is the proper number of empty characters to read.

        :param data: BytesIO stream of bencoded binary data
        :return:     decoded string
        :raises:     DecodeError
        """
        data.seek(-1, 1)
        string_len = self._parse_num(data, delimiter=_Delims.DIVIDER)

        try:
            string_val = data.read(string_len)
        except:
            logger.error(f"Unable to read specified string length {string_len}")
            raise DecodeError

        if len(string_val) != string_len:
            logger.error(f"Unable to read specified string length {string_len}")
            raise DecodeError
        return string_val

    def _parse_num(self, data: BytesIO, delimiter: bytes) -> int:
        """
        parses an bencoded integer up to specified delimiter from a BytesIO buffer.

        :param data:
        :param delimiter: delimiter do indicate the end of the number
        :return:          decoded number
        :raises:          DecodeError
        """
        parsed_num = bytes()
        while True:
            char = data.read(1)
            if char not in _Delims.DIGITS + [b"-"] or char == '':
                if char != delimiter:
                    logger.error(
                        "Invalid character while parsing integer. Found {wrong}, expected {right}".format(wrong=char,
                                                                                                          right=delimiter))
                    raise DecodeError
                else:
                    break
            parsed_num += char

        num_str = parsed_num.decode("ASCII")
        if len(num_str) == 0:
            logger.error("Empty strings are not allowed for integer keys")
            raise DecodeError
        elif len(num_str) > 1 and (num_str[:2] == '-0' or num_str[0] == '0'):
            logger.error("Leading or negative zeros are not allowed for integer keys")
            raise DecodeError

        return int(num_str)


class Encoder:
    """
    Encodes an OrderedDict and returns the bencoded bytes
    """

    def bencode(self, data: OrderedDict) -> Union[bytes, None]:
        """
        Bencodes an OrderedDict and returns the bencoded string.
        :param data: OrderedDict object to bencode
        :return:     bencoded bytes or None if empty data received
        :raises:     EncodeError
        """
        logger.debug(f"bencoding OrderedDict {data}")

        if len(data) == 0:
            return None

        return self._encode(data)

    def _encode(self, obj: Union[dict, list, bytes, int]) -> bytes:
        """
        Recursively bencodes an OrderedDict
        :param obj: object to decode
        :return:    bencoded string
        :raises:    EncodeError
        """
        if isinstance(obj, dict):
            contents = _Delims.DICT_START
            for k, v in obj.items():
                if not isinstance(k, bytes):
                    logger.error("Dictionary keys must be bytes")
                    raise EncodeError()
                contents += self._encode_bytestr(k)
                contents += self._encode(v)
            contents += _Delims.DICT_END
            return contents
        elif isinstance(obj, list):
            contents = _Delims.LIST_START
            for item in obj:
                val = self._encode(item)
                if val:
                    contents += val
            contents += _Delims.LIST_END
            return contents
        elif isinstance(obj, bytes):
            return self._encode_bytestr(obj)
        elif isinstance(obj, bool):
            logger.error("Boolean values are unsupported")
            raise EncodeError
        elif isinstance(obj, int):
            return self._encode_int(obj)
        else:
            logger.error("Unexpected object found {obj}".format(obj=obj))
            raise EncodeError

    def _encode_int(self, int_obj: int) -> bytes:
        """
        bencodes an integer.
        :param int_obj: integer to bencode
        :return:        bencoded string of the specified integer
        """
        ret = bytes()
        ret += _Delims.NUM_START
        ret += str(int_obj).encode("ASCII")
        ret += _Delims.NUM_END
        return ret

    def _encode_bytestr(self, string_obj: bytes) -> bytes:
        """
        bencode a string of bytes

        :param string_obj: string to bencode
        :return:           bencoded string of the specified string
        """
        ret = bytes()
        ret += str(len(string_obj)).encode("ASCII")
        ret += _Delims.DIVIDER
        ret += string_obj
        return ret
