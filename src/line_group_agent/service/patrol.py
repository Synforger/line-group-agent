"""A task that runs one round of a job at a fixed interval while the app is up.

Started and stopped by the web app with the event dispatcher. A round that fails is
logged by its type and the loop goes on.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class Patrol:
    """Calls `job` every `interval_seconds` on the running event loop."""

    def __init__(self, job: Callable[[], Awaitable[None]], interval_seconds: float) -> None:
        self.job = job
        self.interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start the loop; the first round runs at once, then one per interval."""
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the loop."""
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run(self) -> None:
        while True:
            try:
                await self.job()
            except Exception as error:  # one failed round must not end the patrol
                logger.error("patrol: a round failed (%s)", type(error).__name__)
            await asyncio.sleep(self.interval_seconds)
