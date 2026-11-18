"""A limit on how many requests one member may make to the voting page's API per minute.

Called by the LIFF poll service after the member's ID token is checked.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

WINDOW_SECONDS = 60.0


class RequestLimiter:
    """Counts each member's requests over the last minute."""

    def __init__(self, max_per_minute: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_per_minute = max_per_minute
        self._clock = clock
        self._requests: dict[str, deque[float]] = {}

    def allow(self, user_id: str) -> bool:
        """Count a request of this member and say whether it is within the limit."""
        now = self._clock()
        times = self._requests.setdefault(user_id, deque())
        while times and now - times[0] >= WINDOW_SECONDS:
            times.popleft()
        if len(times) >= self.max_per_minute:
            return False
        times.append(now)
        return True
