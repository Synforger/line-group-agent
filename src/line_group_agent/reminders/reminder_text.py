"""The text the group gets at the time of a reminder.

Pure; called by the reminder sender and the reminder tools. The reminder's own text goes
as it is, with no label in front; the people to call are written as `@name` before it.
TODO: build a real LINE mention (text v2 `<mention>`) from the names, once the mention
feature has landed, and drop the `@name` prefix.
"""

from __future__ import annotations

from line_group_agent.reminders.reminder import Reminder


def reminder_text(reminder: Reminder) -> str:
    """Return the text to send for `reminder`."""
    if not reminder.names:
        return reminder.text
    calls = " ".join(f"@{name}" for name in reminder.names)
    return f"{calls} {reminder.text}"
