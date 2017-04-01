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
logger.setLevel(logging.DEBUG)


class BencodeRecursionError(Exception):
    """
    Raised when the recursion limit is reached.
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
    EOF = b"!"


class Decoder:
    """
    Decodes a benoded bytestring, returning an OrderedDict.
    """

    def __init__(self, data: bytes, recursion_limit: int = 1000):
        """
        Creates a new Decoder object.

        :param data:            the bencoded bytes to decode
        :param recursion_limit: the number of times we'll recursively call into the decoding functions
        """
        if recursion_limit <= 0:
            error_msg = "Recursion limit should be greater than 0."
            logger.error(error_msg)
            raise DecodeError(error_msg)

        if not data:
            error_msg = "No data received."
            logger.error(error_msg)
            raise DecodeError(error_msg)

        self._recursion_limit = recursion_limit
        self._current_iter = 0
        self._set_data(data)

    def _set_data(self, data: bytes) -> None:
        """
        Sets the data used by the decoder.
        Warning: _set_data does not check if the data passed in as an argument exists.
        calling decode() after setting no data will return None

        :param data: bytes of data to decode
        """
        try:
            self.data = BytesIO(data)
            self._current_iter = 0
        except TypeError as te:
            error_msg = f"Cannot decode data. Invalid type of {type(data)}."
            logger.exception(error_msg)
            raise DecodeError(error_msg) from te

    def decode(self) -> Union[OrderedDict, list, bytes, int, None]:
        """
        Decodes a bencoded bytestring, returning the data as python objects

        :return:     decoded torrent info, or None if empty data received
        """
        logger.debug("Decoding bytestream.")
        decoded = self._decode()
        if decoded == _Delims.EOF:
            return
        return decoded

    def _decode(self) -> Union[OrderedDict, list, bytes, int]:
        """
        Recursively decodes a BytesIO buffer of bencoded data

        :return:     torrent info decoded into a python object
        :raises:     DecodeError, BencodeRecursionError
        """
        if self._current_iter > self._recursion_limit:
            error_msg = f"Recursion limit reached."
            logger.error(error_msg)
            raise BencodeRecursionError(error_msg)
        else:
            self._current_iter += 1

        char = self.data.read(1)

        if not char:
            # ends the recursive madness. _Delims.EOF is used to signal we've decoded as far as we can go
            return _Delims.EOF
        if char == _Delims.DICT_END:
            # extraneous end delimiters are ignored -> d3:num3:valee = {"num", "val"}
            return _Delims.EOF
        elif char == _Delims.NUM_START:
            return self._decode_int()
        elif char in _Delims.DIGITS:
            return self._decode_str()
        elif char == _Delims.DICT_START:
            return self._decode_dict()
        elif char == _Delims.LIST_START:
            return self._decode_list()
        else:
            error_msg = f"Unable to bdecode {char}. Invalid bencoding key."
            logger.error(error_msg)
            raise DecodeError(error_msg)

    def _decode_dict(self) -> OrderedDict:
        """
        Decodes a bencoded dictionary into an OrderedDict
        only bytestrings are allowed as keys for bencoded dictionaries
        dictionary keys must be sorted according to their raw bytes

        :return: decoded dictionary as OrderedDict
        :raises: DecodeError
        """
        decoded_dict = OrderedDict()
        keys = []

        while True:
            key = self._decode()
            if key == _Delims.EOF:
                break
            if not isinstance(key, bytes):
                error_msg = f"Invalid dictionary key: {key}. Dictionary keys must be bytestrings."
                logger.error(error_msg)
                raise DecodeError(error_msg)
            val = self._decode()

            decoded_dict.setdefault(key, val)
            keys.append(key)

        if keys != sorted(keys):
            error_msg = f"Invalid dictionary. Keys {keys} are not sorted."
            logger.error(error_msg)
            raise DecodeError(error_msg)

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
            if item == _Delims.EOF:
                break
            decoded_list.append(item)
        return decoded_list

    def _decode_int(self) -> int:
        """
        decodes a bencoded integer from the BytesIO buffer.

        :return:     decoded integer
        """
        return self._parse_num(_Delims.NUM_END)

    def _decode_str(self) -> bytes:
        """
        decodes a bencoded string from the BytesIO buffer.
        whitespace only strings are allowed if there is the proper number of whitespace characters to read.

        :return:     decoded string
        :raises:     DecodeError
        """
        # we've already consumed the byte that will start the string length, go back and get it
        self.data.seek(-1, 1)
        string_len = self._parse_num(_Delims.DIVIDER)
        error_msg = f"Unable to read specified string length {string_len}."

        string_val = self.data.read(string_len)

        if len(string_val) != string_len:
            logger.error(error_msg)
            raise DecodeError(error_msg)

        return string_val

    def _parse_num(self, delimiter: bytes) -> int:
        """
        parses an bencoded integer up to specified delimiter from the BytesIO buffer.

        :param delimiter: delimiter do indicate the end of the number
        :return:          decoded number
        :raises:          DecodeError
        """
        parsed_num = bytes()
        while True:
            char = self.data.read(1)
            if char in _Delims.DIGITS + [b"-"]:  # allow negative integers
                parsed_num += char
            else:
                if char != delimiter:
                    error_msg = f"Invalid character while parsing integer. Found {char} expected {delimiter}."
                    logger.error(error_msg)
                    raise DecodeError(error_msg)
                else:
                    break

        num_str = parsed_num.decode("UTF-8")

        if len(num_str) == 0:
            error_msg = "Empty strings are not allowed for integer keys."
            logger.error(error_msg)
            raise DecodeError(error_msg)
        elif len(num_str) > 1 and (num_str[0] == '0' or num_str[:2] == '-0'):
            error_msg = "Leading or negative zeros are not allowed for integer keys."
            logger.error(error_msg)
            raise DecodeError(error_msg)

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
