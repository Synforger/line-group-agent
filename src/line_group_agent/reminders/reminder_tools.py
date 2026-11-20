"""The tools the model uses for reminders: set one (when, what, and whom to call), list the
waiting ones, and cancel one by its id.

A reminder is sent to the group by the reminder sender at its time, without the model.
Setting one is refused for a time that has passed or is more than 60 days away, past the
group's monthly count, or when the account has few messages left this month. Called by the
service builder, which adds the tools to the client tools.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.reminders.push_left import PushLeft
from line_group_agent.reminders.reminder import GROUP_TIME_ZONE, Reminder, month_of
from line_group_agent.reminders.reminder_book import ReminderBook
from line_group_agent.reminders.reminder_input import (
    MAX_DAYS_AHEAD,
    MAX_NAMES,
    TEXT_MAX_CHARS,
    ReminderInputError,
    due_time_of,
    names_of,
    text_of,
)

SET_REMINDER_TOOL_NAME = "set_reminder"
LIST_REMINDERS_TOOL_NAME = "list_reminders"
CANCEL_REMINDER_TOOL_NAME = "cancel_reminder"
NO_REMINDER_RESULT = "No waiting reminder has that id. Call list_reminders to see the ids."
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def reminder_tools(
    book: ReminderBook,
    push_left: PushLeft,
    *,
    max_per_month: int,
    min_push_left: int,
    clock: Callable[[], datetime],
) -> list[ClientTool]:
    """Return the reminder tools, working on `book`. `max_per_month` is how many reminders a
    group may have fall due in one month; `min_push_left` is the fewest messages the account
    may have left for a new reminder to be taken."""

    def set_reminder(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        now = clock()
        try:
            due = due_time_of(fields.get("when"), now)
            text = text_of(fields.get("text"))
            names = names_of(fields.get("who"))
        except ReminderInputError as error:
            return ToolOutcome(f"{error} Nothing was set.", is_error=True)
        month = month_of(due)
        if book.count_booked(turn.group_id, month) >= max_per_month:
            return ToolOutcome(
                f"This group already has {max_per_month} reminders in {month}, the most it "
                "may have in a month. Nothing was set; tell the members.",
                is_error=True,
            )
        left = push_left.get()
        if left is not None and left < min_push_left:
            return ToolOutcome(
                f"The account has only {left} messages left this month, so no more reminders "
                "are taken now. Nothing was set; tell the members.",
                is_error=True,
            )
        reminder = book.add(turn.group_id, text, due, names)
        return ToolOutcome(f"Set {_line_of(reminder)}")

    def list_reminders(_tool_input: object, turn: ToolTurn) -> ToolOutcome:
        now = clock()
        waiting = book.list_pending(turn.group_id)
        month = month_of(now)
        header = (
            f"It is {_moment_of(now)} now. {book.count_booked(turn.group_id, month)} of "
            f"{max_per_month} reminders of {month} are used."
        )
        if not waiting:
            return ToolOutcome(f"{header} No reminder is waiting.")
        return ToolOutcome("\n".join([header, *(_line_of(reminder) for reminder in waiting)]))

    def cancel_reminder(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        reminder_id = fields.get("id")
        removed = book.cancel(turn.group_id, reminder_id) if isinstance(reminder_id, str) else None
        if removed is None:
            return ToolOutcome(NO_REMINDER_RESULT, is_error=True)
        return ToolOutcome(f"Cancelled {_line_of(removed)}")

    return [
        ClientTool(SET_REMINDER_TOOL_NAME, _set_definition(), set_reminder),
        ClientTool(LIST_REMINDERS_TOOL_NAME, _list_definition(), list_reminders),
        ClientTool(CANCEL_REMINDER_TOOL_NAME, _cancel_definition(), cancel_reminder),
    ]


def _moment_of(moment: datetime) -> str:
    local = moment.astimezone(GROUP_TIME_ZONE)
    return f"{local:%Y-%m-%d} ({WEEKDAYS[local.weekday()]}) {local:%H:%M}"


def _line_of(reminder: Reminder) -> str:
    calls = f" calling {', '.join(reminder.names)}" if reminder.names else ""
    return f"{reminder.id}: {_moment_of(reminder.due_at)}{calls}: {reminder.text}"


def _set_definition() -> dict[str, Any]:
    return {
        "name": SET_REMINDER_TOOL_NAME,
        "description": (
            "Have the group told something at a time you choose, without anyone mentioning "
            "you then. Use it when a member asks for a reminder, or asks you to set one "
            "without saying when or what: then decide both from the conversation and the "
            "itinerary (get_itinerary), and say in your reply, in one line, what you set and "
            "when. Ask a short question only when you cannot decide. The text is sent as it "
            "is, with no label in front, so write it as the message the group should read. "
            f"Times are in Japan time, at least a minute ahead and at most {MAX_DAYS_AHEAD} "
            "days ahead. Each reminder costs one message of the account's monthly allowance, "
            "and a group may have a few a month: the call is refused past that, and then you "
            "tell the members why."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "when": {
                    "type": "string",
                    "description": "Date and time to send, ISO like 2026-11-23T21:00 (Japan time).",
                },
                "text": {
                    "type": "string",
                    "description": f"What to tell the group, up to {TEXT_MAX_CHARS} characters.",
                },
                "who": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"Display names of the members to call, up to {MAX_NAMES}. "
                    "Leave it out to tell the whole group.",
                },
            },
            "required": ["when", "text"],
        },
    }


def _list_definition() -> dict[str, Any]:
    return {
        "name": LIST_REMINDERS_TOOL_NAME,
        "description": (
            "List the group's waiting reminders with their ids, times and texts, and how many "
            "of this month's reminders are used. Call it before cancelling one, and when a "
            "member asks what is set."
        ),
        "input_schema": {"type": "object", "properties": {}},
    }


def _cancel_definition() -> dict[str, Any]:
    return {
        "name": CANCEL_REMINDER_TOOL_NAME,
        "description": (
            "Cancel one waiting reminder by its id from list_reminders. Use it only when a "
            "member asks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "The reminder's id, like r1."}},
            "required": ["id"],
        },
    }
