"""Check and clean the fields of a reminder that come from the model.

Pure functions that give back the clean value or raise `ReminderInputError` with a sentence
the model can act on. Called by the reminder tools.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from line_group_agent._common.one_line import one_line
from line_group_agent.reminders.reminder import GROUP_TIME_ZONE

TEXT_MAX_CHARS = 300
NAME_MAX_CHARS = 40
MAX_NAMES = 10
MAX_DAYS_AHEAD = 60
DATE_ONLY_LENGTH = 10


class ReminderInputError(ValueError):
    """A field that cannot be kept; the message says what to give instead."""


def due_time_of(raw: object, now: datetime) -> datetime:
    """Return the time to remind at, in the group's time zone, or refuse anything that is
    not an ISO date and time, is not later than `now`, or is more than `MAX_DAYS_AHEAD`
    days away. A time without an offset is taken as the group's local time."""
    if not isinstance(raw, str) or len(raw.strip()) <= DATE_ONLY_LENGTH:
        raise ReminderInputError("when must be an ISO date and time, like 2026-11-23T21:00.")
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError:
        raise ReminderInputError(
            "when must be an ISO date and time, like 2026-11-23T21:00."
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=GROUP_TIME_ZONE)
    due = parsed.astimezone(GROUP_TIME_ZONE).replace(second=0, microsecond=0)
    if due <= now:
        raise ReminderInputError(
            f"That time has already passed (it is {now.astimezone(GROUP_TIME_ZONE):%Y-%m-%d %H:%M} "
            "now). Give a later time."
        )
    if due > now + timedelta(days=MAX_DAYS_AHEAD):
        raise ReminderInputError(
            f"Reminders are kept for at most {MAX_DAYS_AHEAD} days ahead; that is further away."
        )
    return due


def text_of(raw: object) -> str:
    """Return what to say, trimmed, or refuse text that is missing or too long."""
    if not isinstance(raw, str) or not raw.strip():
        raise ReminderInputError("text is required: what the group should be told.")
    cleaned = raw.strip()
    if len(cleaned) > TEXT_MAX_CHARS:
        raise ReminderInputError(f"text is over {TEXT_MAX_CHARS} characters; shorten it.")
    return cleaned


def names_of(raw: object) -> tuple[str, ...]:
    """Return the display names to call, each once and as one line, or refuse a value that
    is not a list of names. Nothing (or an empty list) means nobody in particular."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ReminderInputError("who must be a list of display names, or left out.")
    names: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise ReminderInputError("who must be a list of display names, or left out.")
        name = one_line(item, NAME_MAX_CHARS + 1).removeprefix("@").strip()
        if len(name) > NAME_MAX_CHARS:
            raise ReminderInputError(f"A name in who is over {NAME_MAX_CHARS} characters.")
        if name and name not in names:
            names.append(name)
    if len(names) > MAX_NAMES:
        raise ReminderInputError(f"who holds at most {MAX_NAMES} names.")
    return tuple(names)
