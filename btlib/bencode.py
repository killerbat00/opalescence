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
from collections import OrderedDict
from io import BytesIO
from typing import Any

DICT_START = b'd'
DICT_END = b'e'
LIST_START = b'l'
LIST_END = b'e'
NUM_START = b'i'
NUM_END = b'e'
DIVIDER = b':'
DIGITS = [b'0', b'1', b'2', b'3', b'4', b'5', b'6', b'7', b'8', b'9']
VALID_CHARS = [DICT_START, DICT_END, LIST_START, NUM_START, DIVIDER] + DIGITS


class DecodeError(Exception):
    pass


class EncodeError(Exception):
    pass


class PrintError(Exception):
    pass


# -- Publicly exposed methods
def bdecode(bencoded_string: str) -> OrderedDict:
    """
    Decodes a bencoded string, returning an OrderedDict.
    :param bencoded_string:  bencoded string to decode
    :return:                 decoded torrent info as a python object
    """
    try:
        decoded_obj = _decode(BytesIO(bencoded_string))
        return decoded_obj
    except DecodeError as e:
        raise e


def bencode(decoded_obj: OrderedDict) -> str:
    """
    Bencodes an OrderedDict and returns the bencoded string.
    :param decoded_obj: Python object to bencode
    :return:            bencoded string
    """
    try:
        return _encode(decoded_obj)
    except (EnvironmentError, EncodeError) as e:
        raise e


def pretty_print(bdecoded_obj: OrderedDict) -> str:
    """
    Prints a nicely formatted representation of a decoded torrent's python object
    :param bdecoded_obj: object to print
    """
    try:
        return pp_dict(bdecoded_obj)
    except PrintError as pe:
        raise pe


# -- Private methods
# --- decoding
def _decode(torrent_buffer: BytesIO) -> [dict, list, str, int]:
    """
    Recursively decodes a bencoded StringIO torrent_buffer.
    :param torrent_buffer:     torrent_bufferer of string to decode
    :return:                   torrent info decoded into a python object
    """
    char = torrent_buffer.read(1)

    if not char:
        return
    if char not in VALID_CHARS:
        raise DecodeError("Unable to decode file.")
    if char == DICT_END:
        return
    elif char == NUM_START:
        return __decode_int(torrent_buffer)
    elif char in DIGITS:
        return __decode_str(torrent_buffer)
    elif char == DICT_START:
        decoded_dict = OrderedDict()
        keys = []
        while True:
            key = _decode(torrent_buffer)
            if not key:
                break
            val = _decode(torrent_buffer)
            keys.append(key)
            decoded_dict.setdefault(key, val)
        if keys != sorted(keys):
            raise DecodeError("Unable to decode dictionary: keys not sorted.")
        return decoded_dict
    elif char == LIST_START:
        decoded_list = []
        while True:
            item = _decode(torrent_buffer)
            if not item:
                break
            decoded_list.append(item)
        return decoded_list


def __decode_int(torrent_buffer: BytesIO) -> int:
    """
    decodes a bencoded integer from a StringIO buffer.
    :param torrent_buffer:  StringIO object being parsed
    :return:                decoded integer
    """
    torrent_buffer.seek(-1, 1)
    char = torrent_buffer.read(1)
    if char != NUM_START:
        raise DecodeError("Error while parsing integer.\n" +
                          "Found {wrong}, expected {right}.".format(wrong=char,
                                                                    right=NUM_START))
    return __parse_num(torrent_buffer, delimiter=NUM_END)


def __decode_str(torrent_buffer: BytesIO) -> str:
    """
    decodes a bencoded string from a StringIO buffer.
    :param torrent_buffer:  StringIO object being parsed
    :return:                decoded string
    """
    torrent_buffer.seek(-1, 1)
    string_len = __parse_num(torrent_buffer, delimiter=DIVIDER)
    string_val = torrent_buffer.read(string_len).decode('ISO-8859-1')
    if len(string_val) != string_len:
        raise DecodeError("Unable to read specified string length {length}".format(length=string_len))

    return string_val


def __parse_num(torrent_buffer: BytesIO, delimiter: bytes) -> int:
    """
    parses an bencoded integer up to specified delimiter from a StringIO buffer.
    :param torrent_buffer:     StringIO object being parsed
    :param delimiter:          delimiter do indicate the end of the number
    :return:                   decoded number
    """
    parsed_num = bytes()
    while True:
        char = torrent_buffer.read(1)
        if char not in DIGITS or char == '':
            if char != delimiter:
                raise DecodeError("Invalid character while parsing integer.\n" +
                                  "Found {wrong}, expected {right}".format(wrong=char,
                                                                           right=delimiter))
            else:
                break
        parsed_num += char
    return int(parsed_num.decode('ascii'))


# --- encoding
def _encode(obj: Any) -> str:
    """
    Recursively bencodes an OrderedDict
    :param obj:     object to decode
    :return:        bencoded string
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
        raise EncodeError("Unexpected object found {obj}".format(obj=obj))


def _encode_int(int_obj: int) -> str:
    """
    bencodes an integer.
    :param int_obj:     integer to bencode
    :return:            bencoded string of the specified integer
    """
    return "{start}{num}{end}".format(start=NUM_START.decode("ISO-8859-1"),
                                      num=int_obj,
                                      end=NUM_END.decode("ISO-8859-1"))


def _encode_str(string_obj: str) -> str:
    """
    bencode a string.
    :param string_obj:  string to bencode
    :return:            bencoded string of the specified string
    """
    return "{length}{div}{str}".format(length=len(string_obj),
                                       div=DIVIDER.decode("ISO-8859-1"),
                                       str=string_obj)


# --- pretty printing
def pp_list(decoded_list: list, lvl: int = 0) -> None:
    """
    Recursively prints items in a list inside a torrent object
    mutually recursive with pp_dict
    :param decoded_list:    the decoded list
    :param lvl:             current recursion level (used for indentation)
    """
    assert (isinstance(decoded_list, list))
    str_ = ""

    for itm in decoded_list:
        if isinstance(itm, dict):
            str_ += pp_dict(itm, lvl)
        elif isinstance(itm, list):
            str_ += pp_list(itm, lvl)
        elif isinstance(itm, str) or isinstance(itm, int):
            str_ += "{pad}{val}".format(pad="\t" * lvl, val=itm)
        else:
            raise PrintError("Unexpected value {val} in torrent.".format(val=itm))
    return str_


def pp_dict(decoded_dict: dict, lvl: int = 0) -> str:
    """
    Recursively prints keys and values from an OrderedDict representing a torrent
    mutually recursive with pp_list
    :param decoded_dict:    dict to print
    :param lvl:             current recursion level (used for indentation)
    """
    assert (isinstance(decoded_dict, dict))
    str_ = ""

    for k, v in decoded_dict.items():
        str_ += "{pad}{val}\n".format(pad="\t" * lvl, val=k)
        if isinstance(v, dict):
            str_ += pp_dict(v, lvl=lvl + 1)
        elif isinstance(v, list):
            str_ += pp_list(v, lvl=lvl + 1)
        elif isinstance(v, str) or isinstance(v, int):
            str_ += "{pad}{val}\n".format(pad="\t" * (lvl + 1), val=v)
        else:
            raise PrintError("Unexpected value {val} in torrent.".format(val=v))
    return str_
