"""A limit on how many ID tokens LINE may be asked to verify and refuse per minute.

Anyone can send a made-up token to the voting page, and each one makes the agent call LINE
Login. If too many of those calls fail, LINE may slow down the agent's whole channel and
real members would get 503. So failures are counted, in all and for each source address, and
while either count is at its limit the agent no longer asks LINE. Called by the LIFF poll
service around its verify call.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Literal

from line_group_agent.liff.request_limiter import RequestLimiter

EVERYONE = "all"


class VerifyFailureLimiter:
    """Counts failed verifies over the last minute, in all and for each source address."""

    def __init__(
        self,
        max_failures_per_minute: int,
        max_failures_per_source_per_minute: int,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._all = RequestLimiter(max_failures_per_minute, clock=clock)
        self._sources = RequestLimiter(max_failures_per_source_per_minute, clock=clock)

    def blocked_by(self, source: str | None) -> Literal["all", "source"] | None:
        """Return `"all"` or `"source"` when that count is at its limit (so LINE is not to be
        asked), else None. Without a source address only the count of all is looked at."""
        if self._all.is_full(EVERYONE):
            return "all"
        if source is not None and self._sources.is_full(source):
            return "source"
        return None

    def record_failure(self, source: str | None) -> None:
        """Count a verify that LINE refused or whose claims did not pass."""
        self._all.record(EVERYONE)
        if source is not None:
            self._sources.record(source)
