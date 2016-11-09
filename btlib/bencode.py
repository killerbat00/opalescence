# -*- coding: utf-8 -*-

"""
Provides support for decoding a bencoded string into a python OrderedDict,
bencoding a decoded OrderedDict, and pretty printing said OrderedDict.

author: brian houston morrow

public:
    bdecode()
    bencode()
    pretty_print()
"""
import logging

from collections import OrderedDict
from io import BytesIO

DICT_START = b'd'
TOKEN_END = b'e'
LIST_START = b'l'
NUM_START = b'i'
DIVIDER = b':'
DIGITS = b'0123456789-'

logger = logging.getLogger('opalescence.' + __name__)


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


def bdecode(bencoded_data: bytes) -> OrderedDict:
    """
    Decodes a bencoded bytestring, returning an OrderedDict.
    :param bencoded_data: bencoded data to decode
    :return:              decoded torrent info as a python object
    :raises:              DecodeError
    """
    logger.debug("bdecoding bytes")
    try:
        bencoded_bytes = BytesIO(bencoded_data)
    except TypeError as te:
        logger.error("Cannot decode, invalid type of {type}".format(type=type(bencoded_data)))
        raise DecodeError from te
    else:
        return _decode(bencoded_bytes)


def bencode(decoded_data: OrderedDict) -> bytes:
    """
    Bencodes an OrderedDict and returns the bencoded string.
    :param decoded_data: python object to bencode
    :return:             bencoded string
    :raises:             EncodeError
    """
    logger.debug("bencoding OrderedDict {d}".format(d=decoded_data))
    return _encode(decoded_data)


def _decode(data_buffer: BytesIO) -> [OrderedDict, list, bytes, int]:
    """
    Recursively decodes a BytesIO buffer of bencoded data
    :param data_buffer: BytesIO buffer of bencoded data to decode
    :return:            torrent info decoded into a python object
    :raises:            DecodeError
    """
    char = data_buffer.read(1)

    if not char:
        return
    if char == TOKEN_END:
        return
    elif char == NUM_START:
        return _decode_int(data_buffer)
    elif char in DIGITS:
        return _decode_str(data_buffer)
    elif char == DICT_START:
        decoded_dict = OrderedDict()
        keys = []
        while True:
            key = _decode(data_buffer)
            if not key:
                break
            val = _decode(data_buffer)
            keys.append(key)
            decoded_dict.setdefault(key, val)
        if keys != sorted(keys):
            logger.error("Unable to decode bencoded dictionary. Keys are not sorted.")
            raise DecodeError
        return decoded_dict
    elif char == LIST_START:
        decoded_list = []
        while True:
            item = _decode(data_buffer)
            if not item:
                break
            decoded_list.append(item)
        return decoded_list
    else:
        logger.error("Unable to bdecode stream. {char} is invalid bencoded type of value.".format(char=char))
        raise DecodeError


def _decode_int(data_buffer: BytesIO) -> int:
    """
    decodes a bencoded integer from a BytesIO buffer.
    :param data_buffer: BytesIO object being parsed
    :return:            decoded integer
    :raises:            DecodeError
    """
    data_buffer.seek(-1, 1)
    char = data_buffer.read(1)
    if char != NUM_START:
        logger.error(
            "Error while parsing integer. Found {wrong}, expected {right}.".format(wrong=char, right=NUM_START))
        raise DecodeError
    return _parse_num(data_buffer, delimiter=TOKEN_END)


def _decode_str(data_buffer: BytesIO) -> bytes:
    """
    decodes a bencoded string from a BytesIO buffer.
    :param data_buffer: BytesIO object being parsed
    :return:            decoded string
    :raises:            DecodeError
    """
    data_buffer.seek(-1, 1)
    string_len = _parse_num(data_buffer, delimiter=DIVIDER)
    string_val = data_buffer.read(string_len)

    if len(string_val) != string_len:
        logger.error("Unable to read specified string length {length}".format(length=string_len))
        raise DecodeError
    return string_val


def _parse_num(data_buffer: BytesIO, delimiter: bytes) -> int:
    """
    parses an bencoded integer up to specified delimiter from a BytesIO buffer.
    :param data_buffer: BytesIO object being parsed
    :param delimiter:   delimiter do indicate the end of the number
    :return:            decoded number
    :raises:            DecodeError
    """
    parsed_num = bytes()
    while True:
        char = data_buffer.read(1)
        if char not in DIGITS or char == b'':
            if char != delimiter:
                logger.error(
                    "Invalid character while parsing integer. Found {wrong}, expected {right}".format(wrong=char,
                                                                                                      right=delimiter))
                raise DecodeError
            else:
                break
        parsed_num += char
    num_str = parsed_num.decode("utf-8")
    if len(num_str) > 1 and (num_str[:2] == '-0' or num_str[0] == '0'):
        logger.error("Leading or negative zeros are not allowed for integer keys")
        raise DecodeError
    return int(num_str)


# --- encoding
def _encode(obj: [dict, bytes, list, str, int]) -> bytes:
    """
    Recursively bencodes an OrderedDict
    :param obj: object to decode
    :return:    bencoded string
    :raises:    EncodeError
    """
    if isinstance(obj, dict):
        contents = bytearray('d', 'utf-8')
        for k, v in obj.items():
            contents += _encode_bytes(k)
            contents += _encode(v)
        contents += TOKEN_END
        return contents
    elif isinstance(obj, list):
        contents = bytearray('l', 'utf-8')
        for item in obj:
            contents += _encode(item)
        contents += TOKEN_END
        return contents
    elif isinstance(obj, int):
        return _encode_int(obj)
    elif isinstance(obj, bytes):
        return _encode_bytes(obj)
    else:
        logger.error("Unexpected object found {obj}".format(obj=obj))
        raise EncodeError


def _encode_bytes(b: bytes) -> bytes:
    """
    bencodes a stream of bytes
    :param b: bytes to bencode
    :return:  bencoded bytes
    """
    result = bytearray()
    result += str.encode(str(len(b)))
    result += b':'
    result += b
    return result


def _encode_int(int_obj: int) -> bytes:
    """
    bencodes an integer.
    :param int_obj: integer to bencode
    :return:        bencoded string of the specified integer
    :raises:        EncodeError
    """
    if not isinstance(int_obj, int):
        logger.error("Unexpected type {type}. Expected int.".format(type=type(int_obj)))
        raise EncodeError
    return str.encode('i' + str(int_obj) + 'e')
