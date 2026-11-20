"""One reminder: what to say to the group, when, and whom to call, with where it stands.

Plain values only; held by the reminder book and read by the tools and the sender.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

# The groups this agent serves are in Japan, so a time given without an offset is Japan's.
GROUP_TIME_ZONE = timezone(timedelta(hours=9))


class ReminderState(StrEnum):
    """Where a reminder stands: waiting, sent, left unsent because the agent was down for
    more than the late limit, or given up after the send failed twice."""

    PENDING = "pending"
    SENT = "sent"
    MISSED = "missed"
    FAILED = "failed"


@dataclass(frozen=True)
class Reminder:
    """`text` is what the group is told at `due_at` (an aware time); `names` are the display
    names to call, possibly none; `attempts` counts the sends that failed."""

    id: str
    text: str
    due_at: datetime
    names: tuple[str, ...]
    created_at: datetime
    state: ReminderState = ReminderState.PENDING
    attempts: int = 0


def month_of(moment: datetime) -> str:
    """Return the month of `moment` in the group's time zone, like `2026-11`."""
    return moment.astimezone(GROUP_TIME_ZONE).strftime("%Y-%m")
