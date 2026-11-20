"""How many members a group has, as LINE counts them, remembered for an hour per group.

Called by the answerer, which tells the model the size of the group next to the names the
records know, so that a member who has not spoken yet is still counted.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

HEADCOUNT_REMEMBER_SECONDS = 3600


class MemberCounter(Protocol):
    """What the headcount needs from LINE."""

    async def get_member_count(self, group_id: str) -> int | None: ...


class GroupHeadcount:
    """Asks LINE for the number of members of a group and remembers the answer."""

    def __init__(
        self, counter: MemberCounter, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._counter = counter
        self._clock = clock
        self._remembered: dict[str, tuple[int, float]] = {}

    async def count_of(self, group_id: str) -> int | None:
        """Return the group's member count, or None when LINE does not give it. A count that
        was not given is asked for again on the next call."""
        now = self._clock()
        remembered = self._remembered.get(group_id)
        if remembered is not None and now - remembered[1] < HEADCOUNT_REMEMBER_SECONDS:
            return remembered[0]
        count = await self._counter.get_member_count(group_id)
        if count is None:
            return None
        self._remembered[group_id] = (count, now)
        return count
