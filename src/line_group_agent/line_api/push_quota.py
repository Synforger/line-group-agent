"""How many messages the account may still send this month, asked of LINE at most once
an hour.

Called by the wait notice, which only sends its message when enough pushes are left
for the real answer. The answer is kept for an hour; a failed question is not kept.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

CACHE_SECONDS = 3600.0


class QuotaLine(Protocol):
    """What the quota needs from the LINE client."""

    async def get_remaining_messages(self) -> int | None: ...


class PushQuota:
    """The remaining monthly messages, cached for an hour."""

    def __init__(
        self,
        line: QuotaLine,
        *,
        clock: Callable[[], float] = time.monotonic,
        cache_seconds: float = CACHE_SECONDS,
    ) -> None:
        self.line = line
        self._clock = clock
        self._cache_seconds = cache_seconds
        self._remaining: int | None = None
        self._asked_at: float | None = None

    async def remaining(self) -> int | None:
        """Return the messages left this month, or None when LINE does not say."""
        now = self._clock()
        if self._asked_at is not None and now - self._asked_at < self._cache_seconds:
            return self._remaining
        remaining = await self.line.get_remaining_messages()
        if remaining is None:
            return None
        self._remaining, self._asked_at = remaining, now
        return remaining
