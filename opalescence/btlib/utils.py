import asyncio
import errno
import os
from pathlib import Path

__all__ = ["ensure_dir_exists", "open_peer_connection"]


def ensure_dir_exists(filename: Path) -> None:
    """
    Ensures the directories specified in the given path exist,
    creating them if not.

    :param filename: Path-like object whose containing directories to ensure exist.
    :raises OSError: except EEXIST
    """
    if not os.path.exists(os.path.dirname(filename)):
        try:
            os.makedirs(os.path.dirname(filename))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise


async def open_peer_connection(host=None, port=None) -> [asyncio.StreamReader, asyncio.StreamWriter]:
    """
    A wrapper for asyncio.open_connection() returning a (reader, writer) pair.
    """
    loop = asyncio.events.get_event_loop()
    reader = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(reader, loop=loop)
    transport, _ = await loop.create_connection(
        lambda: protocol, host, port)
    transport.set_write_buffer_limits(0)  # let the OS handle buffering
    writer = asyncio.StreamWriter(transport, protocol, reader, loop)
    return reader, writer
