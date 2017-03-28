# -*- coding: utf-8 -*-

"""
Provides support for decoding a bencoded string into a python OrderedDict,
bencoding a decoded OrderedDict, and pretty printing said OrderedDict.

author: brian houston morrow

public:
    bdecode()
    bencode()
"""
import logging

from collections import OrderedDict
from io import BytesIO
from typing import Union

DICT_START = b'd'
DICT_END = b'e'
LIST_START = b'l'
LIST_END = b'e'
NUM_START = b'i'
NUM_END = b'e'
DIVIDER = b':'
DIGITS = [b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']
VALID_CHARS = [DICT_START, DICT_END, LIST_START, NUM_START, DIVIDER] + DIGITS

# controls how many times _deocode and _encode will be recursively called before raising a BencodeRecursionError
RECURSION_LIMIT = 1000
CURRENT_ITER = 0

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


def bdecode(bencoded_data: bytes) -> Union[OrderedDict, None]:
    """
    Decodes a bencoded bytestring, returning an OrderedDict.
    :param bencoded_data: bencoded data to decode
    :return:              decoded torrent info as a python object
                          or None if empty bytes received
    :raises:              DecodeError
    """
    logger.debug("bdecoding bytes")

    if len(bencoded_data) == 0:
        return None

    try:
        bencoded_bytes = BytesIO(bencoded_data)
    except TypeError as te:
        logger.error(f"Cannot decode, invalid type of {type(bencoded_data)}")
        raise DecodeError from te
    else:
        return _decode(bencoded_bytes)


def bencode(decoded_data: OrderedDict) -> str:
    """
    Bencodes an OrderedDict and returns the bencoded string.
    :param decoded_data: python object to bencode
    :return:             bencoded string
    :raises:             EncodeError
    """
    logger.debug(f"bencoding OrderedDict {decoded_data}")
    return _encode(decoded_data)


# TODO: implement a max recursion limit
def _decode(data_buffer: BytesIO) -> Union[OrderedDict, list, str, int]:
    """
    Recursively decodes a BytesIO buffer of bencoded data

    :param data_buffer: BytesIO buffer of bencoded data to decode
    :return:            torrent info decoded into a python object
    :raises:            DecodeError, BencodeRecursionError
    """
    global CURRENT_ITER, RECURSION_LIMIT

    if CURRENT_ITER > RECURSION_LIMIT:
        logger.error(f"Recursion limit of {RECURSION_LIMIT} reached.")
        raise BencodeRecursionError
    else:
        CURRENT_ITER += 1

    char = data_buffer.read(1)

    if not char:
        return
    if char == DICT_END:
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
        logger.error(f"Unable to bdecode stream. {char} is invalid bencoded type of value.")
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
            f"Error while parsing integer. Found {char}, expected {NUM_START}.")
        raise DecodeError
    return _parse_num(data_buffer, delimiter=NUM_END)


def _decode_str(data_buffer: BytesIO) -> str:
    """
    decodes a bencoded string from a BytesIO buffer.
    :param data_buffer: BytesIO object being parsed
    :return:            decoded string
    :raises:            DecodeError
    """
    data_buffer.seek(-1, 1)
    string_len = _parse_num(data_buffer, delimiter=DIVIDER)
    string_val = data_buffer.read(string_len).decode('ISO-8859-1')

    if len(string_val) != string_len:
        logger.error(f"Unable to read specified string length {string_len}")
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
        if char not in DIGITS + [b"-"] or char == '':
            if char != delimiter:
                logger.error(
                    "Invalid character while parsing integer. Found {wrong}, expected {right}".format(wrong=char,
                                                                                                      right=delimiter))
                raise DecodeError
            else:
                break
        parsed_num += char
    num_str = parsed_num.decode("ISO-8859-1")
    if len(num_str) > 1 and (num_str[:2] == '-0' or num_str[0] == '0'):
        logger.error("Leading or negative zeros are not allowed for integer keys")
        raise DecodeError
    return int(num_str)


# --- encoding
def _encode(obj: [dict, list, str, int]) -> str:
    """
    Recursively bencodes an OrderedDict
    :param obj: object to decode
    :return:    bencoded string
    :raises:    EncodeError
    """
    if isinstance(obj, dict):
        contents = DICT_START.decode("ISO-8859-1")
        for k, v in obj.items():
            contents += _encode_str(k)
            contents += _encode(v)
        contents += DICT_END.decode("ISO-8859-1")
        return contents
    elif isinstance(obj, list):
        contents = LIST_START.decode("ISO-8859-1")
        for item in obj:
            contents += _encode(item)
        contents += LIST_END.decode("ISO-8859-1")
        return contents
    elif isinstance(obj, str):
        return _encode_str(obj)
    elif isinstance(obj, int):
        return _encode_int(obj)
    else:
        logger.error("Unexpected object found {obj}".format(obj=obj))
        raise EncodeError


def _encode_int(int_obj: int) -> str:
    """
    bencodes an integer.
    :param int_obj: integer to bencode
    :return:        bencoded string of the specified integer
    """
    return "{start}{num}{end}".format(start=NUM_START.decode("ISO-8859-1"),
                                      num=int_obj,
                                      end=NUM_END.decode("ISO-8859-1"))


def _encode_str(string_obj: str) -> str:
    """
    bencode a string
    :param string_obj: string to bencode
    :return:           bencoded string of the specified string
    """
    return "{length}{div}{str}".format(length=len(string_obj),
                                       div=DIVIDER.decode("ISO-8859-1"),
                                       str=string_obj)

