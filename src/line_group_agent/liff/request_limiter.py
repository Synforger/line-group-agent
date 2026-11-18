"""A limit on how many times something may happen per minute for each key (a member, a source
address, or everything at once).

Called by the LIFF poll service for a member's requests, and by the verify failure limiter.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0
SWEEP_ABOVE_KEYS = 1000


class RequestLimiter:
    """Counts the events of each key over the last minute. A key is forgotten once its last
    event is a minute old, so keys made up by a caller do not pile up."""

    def __init__(self, max_per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_per_minute = max_per_minute
        self._clock = clock
        self._requests: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        """Count an event of this key and say whether it is within the limit. An event over
        the limit is not counted."""
        if self.is_full(key):
            return False
        self.record(key)
        return True

    def is_full(self, key: str) -> bool:
        """Say whether this key has already reached the limit in the last minute, without
        counting anything."""
        times = self._requests.get(key)
        if times is None:
            return False
        self._drop_old(times, self._clock())
        return len(times) >= self.max_per_minute

    def record(self, key: str) -> None:
        """Count an event of this key."""
        now = self._clock()
        if len(self._requests) > SWEEP_ABOVE_KEYS:
            self._forget_idle_keys(now)
        times = self._requests.setdefault(key, deque())
        self._drop_old(times, now)
        times.append(now)

    def _forget_idle_keys(self, now: float) -> None:
        for key in list(self._requests):
            times = self._requests[key]
            self._drop_old(times, now)
            if not times:
                del self._requests[key]

    @staticmethod
    def _drop_old(times: deque[float], now: float) -> None:
        while times and now - times[0] >= WINDOW_SECONDS:
            times.popleft()
