"""The text the group gets at the time of a reminder.

Pure; called by the reminder sender and the reminder tools. The reminder's own text goes
as it is, with no label in front; the people to call are written before it as mentions
(`<mention>name</mention>`, which the LINE client makes a real mention) when the group's
record knows them, and as `@name` otherwise.
"""

from __future__ import annotations

from collections.abc import Mapping

from line_group_agent.reminders.reminder import Reminder


def reminder_text(reminder: Reminder, mentionable: Mapping[str, str] | None = None) -> str:
    """Return the text to send for `reminder`; a name that is a key of `mentionable` (name to
    user id) is marked for a mention, any other is written `@name`."""
    if not reminder.names:
        return reminder.text
    known = mentionable or {}
    calls = " ".join(f"<mention>{n}</mention>" if n in known else f"@{n}" for n in reminder.names)
    return f"{calls} {reminder.text}"
