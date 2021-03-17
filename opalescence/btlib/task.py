from __future__ import annotations

import asyncio
import logging
from typing import Coroutine, Iterable, Optional, Set

logger = logging.getLogger(__name__)


class MonitoredTask:
    """
    A wrapper for a task being executed asynchronously.
    Each task can have a parent and children. `Tasks` are responsible
    for handling the failures of their children and can automatically restart
    them if necessary. When a `Task` is cancelled, so are the children.
    """

    def __init__(self, name: str, coros: Iterable[Coroutine]):
        self._name = name
        self._task: Optional[asyncio.Task] = None
        self._coros: Iterable[Coroutine] = set(coros)
        self._tasks: Set[asyncio.Task] = set()

    def start(self) -> None:
        if self._task is not None:
            return  # log? starting already running task.
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task is None:
            return
        t = self._task
        self._task = None
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run(self) -> None:
        self._tasks = {asyncio.create_task(coro) for coro in self._coros}
        try:
            await asyncio.gather(*self._tasks)
        except Exception as e:
            logger.exception(f"{self._name} : Exception encountered {type(e).__name__}", exc_info=True)

    async def __aenter__(self):
        self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
        return False
