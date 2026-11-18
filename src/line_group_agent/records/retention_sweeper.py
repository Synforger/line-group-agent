"""Delete what is older than the retention period from the group records and the
conversation records, once a day.

Called by the group watcher at each patrol. The running generation of a conversation is
never touched, and neither are the summaries in the group's journal. A group's record
keeps what the running conversation might still look up, the same way.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog

logger = logging.getLogger(__name__)

SWEEP_INTERVAL = timedelta(days=1)


class RetentionSweeper:
    """Removes expired messages and conversation rows, at most once a day."""

    def __init__(
        self,
        conversations: GroupConversations,
        group_log: GroupLog,
        retention_days: int,
        clock: Callable[[], datetime],
    ) -> None:
        self.conversations = conversations
        self.group_log = group_log
        self.retention = timedelta(days=retention_days)
        self._clock = clock
        self._swept_at: datetime | None = None

    async def sweep_if_due(self) -> int:
        """Sweep every known group when a day has passed since the last sweep (the first
        call sweeps at once). Return how many messages and rows were deleted."""
        now = self._clock()
        if self._swept_at is not None and now - self._swept_at < SWEEP_INTERVAL:
            return 0
        self._swept_at = now
        cutoff = now - self.retention
        deleted = 0
        for conversation in self.conversations.list():
            async with conversation.lock:
                deleted += len(
                    self.group_log.remove_older_than(
                        conversation.group_id, cutoff, keep_since=conversation.live_since
                    )
                )
                deleted += conversation.drop_rows_before(cutoff)
        if deleted:
            logger.info("retention: %d expired message(s) and row(s) deleted", deleted)
        return deleted
