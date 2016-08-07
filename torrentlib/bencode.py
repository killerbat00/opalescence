"""
Provides support for decoding a bencoded string into a python OrderedDict,
bencoding a decoded OrderedDict, and pretty printing said OrderedDict.

author: brian houston morrow

public:
    bdecode()
    bencode()
    pretty_print()
"""
import string
import types
from StringIO import StringIO
from collections import OrderedDict

import utils.decorators

DICT_START = "d"
DICT_END = "e"
LIST_START = "l"
LIST_END = "e"
NUM_START = "i"
NUM_END = "e"
DIVIDER = ":"


class DecodeError(Exception):
    pass


class EncodeError(Exception):
    pass


class PrintError(Exception):
    pass


# -- Publicly exposed methods
@utils.decorators.log_this
def bdecode(bencoded_string):
    # type: (str) -> OrderedDict
    """
    Decodes a bencoded string, returning an OrderedDict.
    :param bencoded_string:  bencoded string to decode
    :return:                 decoded torrent info as a python object
    """
    assert (isinstance(bencoded_string, types.StringType))

    try:
        decoded_obj = _decode(StringIO(bencoded_string))
        return decoded_obj
    except DecodeError as e:
        raise e


@utils.decorators.log_this
def bencode(decoded_obj):
    # type (OrderedDict) -> str
    """
    Bencodes an OrderedDict and returns the bencoded string.
    :param decoded_obj: Python object to bencode
    :return:            bencoded string
    """
    assert (isinstance(decoded_obj, types.DictionaryType))

    try:
        return _encode(decoded_obj)
    except (EnvironmentError, EncodeError) as e:
        raise e


@utils.decorators.log_this
def pretty_print(bdecoded_obj):
    # type (OrderedDict, int) -> None
    """
    Prints a nicely formatted representation of a decoded torrent's python object
    :param bdecoded_obj: object to print
    """
    assert (isinstance(bdecoded_obj, types.DictionaryType))
    try:
        pp_dict(bdecoded_obj)
    except PrintError as pe:
        raise pe


# -- Private methods
# --- decoding
@utils.decorators.log_this
def _decode(torrent_buffer):
    # type (StringIO) -> OrderedDict
    """
    Recursively decodes a bencoded StringIO torrent_buffer.
    :param torrent_buffer:     torrent_bufferer of string to decode
    :return:                   torrent info decoded into a python object
    """
    char = torrent_buffer.read(1)

    if not char:
        return
    if char == DICT_END:
        return
    elif char == NUM_START:
        return _decode_int(torrent_buffer)
    elif char in string.digits:
        return _decode_str(torrent_buffer)
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
    else:
        raise DecodeError("Unable to decode file.")


@utils.decorators.log_this
def _decode_int(torrent_buffer):
    # type (StringIO) -> int
    """
    decodes a bencoded integer from a StringIO buffer.
    :param torrent_buffer:  StringIO object being parsed
    :return:                decoded integer
    """
    torrent_buffer.seek(-1, 1)
    char = torrent_buffer.read(1)
    if char != NUM_START:
        raise DecodeError("Error while parsing integer.\n" +
                          "Found {wrong} at position {pos}, expected {right}.".format(wrong=char,
                                                                                      pos=torrent_buffer.pos,
                                                                                      right=NUM_START))
    return _parse_num(torrent_buffer, delimiter=NUM_END)


@utils.decorators.log_this
def _decode_str(torrent_buffer):
    # type (StringIO) -> str
    """
    decodes a bencoded string from a StringIO buffer.
    :param torrent_buffer:  StringIO object being parsed
    :return:                decoded string
    """
    torrent_buffer.seek(-1, 1)
    string_len = _parse_num(torrent_buffer, delimiter=DIVIDER)
    return torrent_buffer.read(string_len)


@utils.decorators.log_this
def _parse_num(torrent_buffer, delimiter):
    # type (StringIO, str) -> int
    """
    parses an bencoded integer up to specified delimiter from a StringIO buffer.
    :param torrent_buffer:     StringIO object being parsed
    :param delimiter:          delimiter do indicate the end of the number
    :return:                   decoded number
    """
    parsed_num = ''
    while True:
        char = torrent_buffer.read(1)
        if char not in string.digits or char == '':
            if char != delimiter:
                raise DecodeError("Invalid character while parsing integer.\n" +
                                  "Found {wrong} at {pos}, expected {right}".format(wrong=char,
                                                                                    pos=torrent_buffer.pos,
                                                                                    right=delimiter))
            else:
                break
        parsed_num += char
    return int(parsed_num)


# --- encoding
@utils.decorators.log_this
def _encode(obj):
    # type (?) -> str
    """
    Recursively bencodes an OrderedDict
    :param obj:     object to decode
    :return:        bencoded string
    """
    if isinstance(obj, types.DictionaryType):
        contents = DICT_START
        for k, v in obj.iteritems():
            contents += _encode_str(k)
            contents += _encode(v)
        contents += DICT_END
        return contents

    elif isinstance(obj, types.ListType):
        contents = ''
        contents += LIST_START
        for item in obj:
            contents += _encode(item)
        contents += LIST_END
        return contents

    elif isinstance(obj, types.StringType):
        return _encode_str(obj)

    elif isinstance(obj, types.IntType):
        return _encode_int(obj)

    else:
        raise EncodeError("Unexpected object found {obj}".format(obj=obj))


@utils.decorators.log_this
def _encode_int(int_obj):
    # type (int) -> str
    """
    bencodes an integer.
    :param int_obj:     integer to bencode
    :return:            bencoded string of the specified integer
    """
    return "{start}{num}{end}".format(start=NUM_START,
                                      num=int_obj,
                                      end=NUM_END)


@utils.decorators.log_this
def _encode_str(string_obj):
    # type (str) -> str
    """
    bencode a string.
    :param string_obj:  string to bencode
    :return:            bencoded string of the specified string
    """
    return "{length}{div}{str}".format(length=len(string_obj),
                                       div=DIVIDER,
                                       str=string_obj)


# --- pretty printing
@utils.decorators.log_this
def pp_list(decoded_list, lvl=None):
    # type (list, int) -> None
    """
    Recursively prints items in a list inside a torrent object
    mutually recursive with pp_dict
    :param decoded_list:    the decoded list
    :param lvl:             current recursion level (used for indentation)
    """
    assert (isinstance(decoded_list, types.ListType))

    if lvl is None:
        lvl = 0

    for itm in decoded_list:
        if isinstance(itm, types.DictionaryType):
            pp_dict(itm, lvl)
        elif isinstance(itm, types.ListType):
            pp_list(itm, lvl)
        elif isinstance(itm, types.StringType) or isinstance(itm, types.IntType):
            print("\t" * lvl + itm)
        else:
            raise PrintError("Unexpected value {val} in torrent.".format(val=itm))


@utils.decorators.log_this
def pp_dict(decoded_dict, lvl=None):
    # type (OrderedDict, int) -> None
    """
    Recursively prints keys and values from an OrderedDict representing a torrent
    mutually recursive with pp_list
    :param decoded_dict:    dict to print
    :param lvl:             current recursion level (used for indentation)
    """
    assert (isinstance(decoded_dict, types.DictionaryType))

    if lvl is None:
        lvl = 0

    for k, v in decoded_dict.iteritems():
        print("\t" * lvl + k)
        if isinstance(v, types.DictionaryType):
            pp_dict(v, lvl=lvl + 1)
        elif isinstance(v, types.ListType):
            pp_list(v, lvl=lvl + 1)
        elif isinstance(v, types.StringType) or isinstance(v, types.IntType):
            print("\t" * (lvl + 1) + str(v))
        else:
            raise PrintError("Unexpected value {val} in torrent.".format(val=v))
