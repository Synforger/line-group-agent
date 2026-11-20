"""How many messages the account may still send this month, as last asked of LINE.

The tools run without waiting, so they cannot ask LINE themselves; the sender refreshes this
at each round (the quota keeps its answer for an hour, so LINE is asked about hourly) and
the tools read it. Called by the reminder sender and the reminder tools.
"""

from __future__ import annotations

from line_group_agent.line_api.push_quota import PushQuota


class PushLeft:
    """The messages left this month as of the last refresh; None until LINE has said."""

    def __init__(self, quota: PushQuota) -> None:
        self._quota = quota
        self._left: int | None = None

    async def refresh(self) -> None:
        """Ask the quota again; an answer that does not come leaves the last one."""
        left = await self._quota.remaining()
        if left is not None:
            self._left = left

    def get(self) -> int | None:
        """Return the messages left as of the last refresh, or None when not known."""
        return self._left
