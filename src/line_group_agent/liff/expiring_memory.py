"""A small memory whose entries are forgotten after a while.

Called by the LIFF member lookups to remember who is in a group and what a member is called,
so a page that is opened over and over asks LINE once in a few minutes.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class ExpiringMemory[Key, Value]:
    """Keeps up to `max_entries` values for `ttl_seconds` each; the oldest go first."""

    def __init__(
        self,
        ttl_seconds: float,
        *,
        max_entries: int = 1000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: dict[Key, tuple[Value, float]] = {}

    def get(self, key: Key) -> Value | None:
        """Return the remembered value, or None when there is none or it has expired."""
        entry = self._entries.get(key)
        if entry is None:
            return None
        value, remembered_at = entry
        if self._clock() - remembered_at >= self.ttl_seconds:
            del self._entries[key]
            return None
        return value

    def remember(self, key: Key, value: Value) -> None:
        """Keep the value from now on, replacing an earlier one for the key."""
        self._entries.pop(key, None)
        self._entries[key] = (value, self._clock())
        while len(self._entries) > self.max_entries:
            del self._entries[next(iter(self._entries))]
