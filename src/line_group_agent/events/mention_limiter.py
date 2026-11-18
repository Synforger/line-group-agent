"""Keep one person from calling the bot over and over: a limit on mentions per hour.

Called by the event dispatcher for each mention it is about to answer. A person over
the limit is not answered; they are told once, the first time they pass it, and not
again until they are let through again.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from enum import StrEnum

WINDOW_SECONDS = 3600.0


class MentionVerdict(StrEnum):
    """What to do with a mention."""

    ANSWER = "answer"
    REFUSE_AND_TELL = "refuse_and_tell"
    REFUSE = "refuse"


class MentionLimiter:
    """Counts each person's answered mentions over the last hour."""

    def __init__(self, max_per_hour: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_per_hour = max_per_hour
        self._clock = clock
        self._answered: dict[str, deque[float]] = {}
        self._told: set[str] = set()

    def check(self, user_id: str | None) -> MentionVerdict:
        """Decide a mention of this person and count it when it is to be answered.
        A mention without a known person is always answered."""
        if user_id is None:
            return MentionVerdict.ANSWER
        now = self._clock()
        times = self._answered.setdefault(user_id, deque())
        while times and now - times[0] >= WINDOW_SECONDS:
            times.popleft()
        if len(times) >= self.max_per_hour:
            if user_id in self._told:
                return MentionVerdict.REFUSE
            self._told.add(user_id)
            return MentionVerdict.REFUSE_AND_TELL
        times.append(now)
        self._told.discard(user_id)
        return MentionVerdict.ANSWER
