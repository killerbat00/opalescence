# -*- coding: utf-8 -*-

"""
Utilities used when testing.
"""
import asyncio
from unittest import mock


def async_run(coro):
    """
    runs the specified asynchronous coroutine once in an event loop

    :param coro: coroutine to run
    :return:     the result of the coroutine
    """
    return asyncio.get_event_loop().run_until_complete(coro)


def create_async_mock(data: bytes = None, status: int = None):
    """
    Creates a subclassed MagicMock that will behaves like an async coroutine and that can be used
    to replace an object used in an async with statement
    :param data:   data that will be returned when the mock connection is read
    :param status: the mock connection's status
    """

    class AsyncMock(mock.MagicMock):
        """
        Mock class that works with an async context manager. Currently used to mock aiohttp.ClientSession.get
        the ClientResponse is a MagicMock with the specified data and status.
        """

        async def __aenter__(self):
            conn = mock.MagicMock()
            f = asyncio.Future()
            f.set_result(data)
            conn.read = mock.MagicMock(return_value=f)
            type(conn).status = mock.PropertyMock(return_value=status)
            return conn

        async def __aexit__(self, *_):
            pass

        def __await__(self):
            yield

    return AsyncMock()
