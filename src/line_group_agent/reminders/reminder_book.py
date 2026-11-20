"""The reminders of every group.

Lives at `<state_dir>/groups/<groupId>/reminders.json`, one file per group, replaced whole at
each change: `{"last_number", "reminders": [{"id", "text", "due_at", "names", "created_at",
"state", "attempts"}]}`. A reminder that was cancelled is removed; one that was sent, missed
or given up stays for `KEEP_FINISHED_DAYS` days so the month's count can be told. Every
method reads and writes without waiting, so the tools and the sender, which run on the same
event loop, never see a half change. Called by the reminder tools and the reminder sender.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from line_group_agent.records.group_folder import group_folder
from line_group_agent.records.group_log import GROUP_ID_PATTERN
from line_group_agent.records.json_document import read_json_document, write_json_document
from line_group_agent.reminders.reminder import Reminder, ReminderState, month_of

REMINDERS_FILE_NAME = "reminders.json"
REMINDER_ID_PREFIX = "r"
KEEP_FINISHED_DAYS = 40


@dataclass(frozen=True)
class DueReminder:
    """A reminder whose time has come, with the group it belongs to."""

    group_id: str
    reminder: Reminder


class ReminderBook:
    """Reads and changes the reminders under one state folder."""

    def __init__(self, state_dir: Path, clock: Callable[[], datetime]) -> None:
        self.state_dir = state_dir
        self._clock = clock

    def add(self, group_id: str, text: str, due_at: datetime, names: tuple[str, ...]) -> Reminder:
        """Keep a new reminder (the caller has checked it) and return it with its id."""
        document = self._read(group_id)
        existing = _reminders_of(document)
        number = max(_last_number_of(document), *(_number_of(r.id) for r in existing), 0) + 1
        reminder = Reminder(
            id=f"{REMINDER_ID_PREFIX}{number}",
            text=text,
            due_at=due_at,
            names=names,
            created_at=self._clock(),
        )
        self._write(group_id, number, [*existing, reminder])
        return reminder

    def list_pending(self, group_id: str) -> list[Reminder]:
        """Return the reminders still waiting, the soonest first."""
        waiting = [r for r in self._all(group_id) if r.state is ReminderState.PENDING]
        return sorted(waiting, key=lambda reminder: reminder.due_at)

    def count_booked(self, group_id: str, month: str) -> int:
        """Return how many reminders of this group fall due in `month` (like `2026-11`) and
        were, or will be, sent: those waiting and those sent."""
        return sum(
            1
            for reminder in self._all(group_id)
            if reminder.state in (ReminderState.PENDING, ReminderState.SENT)
            and month_of(reminder.due_at) == month
        )

    def cancel(self, group_id: str, reminder_id: str) -> Reminder | None:
        """Remove a waiting reminder and return it, or None when no waiting reminder has this
        id."""
        document = self._read(group_id)
        reminders = _reminders_of(document)
        found = _pending_with_id(reminders, reminder_id)
        if found is None:
            return None
        kept = [reminder for reminder in reminders if reminder.id != found.id]
        self._write(group_id, _last_number_of(document), kept)
        return found

    def due(self, now: datetime) -> list[DueReminder]:
        """Return the waiting reminders of every group whose time is `now` or earlier,
        the earliest first."""
        found = [
            DueReminder(group_id, reminder)
            for group_id in self._group_ids()
            for reminder in self.list_pending(group_id)
            if reminder.due_at <= now
        ]
        return sorted(found, key=lambda due: due.reminder.due_at)

    def finish(self, group_id: str, reminder_id: str, state: ReminderState) -> None:
        """Mark a waiting reminder as sent, missed or failed."""
        self._change(group_id, reminder_id, lambda reminder: replace(reminder, state=state))

    def note_failed_attempt(self, group_id: str, reminder_id: str) -> None:
        """Count one failed send of a waiting reminder; it stays waiting."""
        self._change(
            group_id,
            reminder_id,
            lambda reminder: replace(reminder, attempts=reminder.attempts + 1),
        )

    def _change(
        self, group_id: str, reminder_id: str, change: Callable[[Reminder], Reminder]
    ) -> None:
        document = self._read(group_id)
        reminders = _reminders_of(document)
        found = _pending_with_id(reminders, reminder_id)
        if found is None:
            return
        changed = [change(r) if r.id == found.id else r for r in reminders]
        self._write(group_id, _last_number_of(document), changed)

    def _all(self, group_id: str) -> list[Reminder]:
        return _reminders_of(self._read(group_id))

    def _group_ids(self) -> list[str]:
        try:
            folders = sorted((self.state_dir / "groups").iterdir())
        except OSError:
            return []
        return [folder.name for folder in folders if GROUP_ID_PATTERN.match(folder.name)]

    def _write(self, group_id: str, last_number: int, reminders: list[Reminder]) -> None:
        horizon = self._clock() - timedelta(days=KEEP_FINISHED_DAYS)
        kept = [
            reminder
            for reminder in reminders
            if reminder.state is ReminderState.PENDING or reminder.due_at >= horizon
        ]
        write_json_document(
            self._path(group_id),
            {"last_number": last_number, "reminders": [_row_of(r) for r in kept]},
        )

    def _read(self, group_id: str) -> dict[str, Any]:
        return read_json_document(self._path(group_id))

    def _path(self, group_id: str) -> Path:
        return group_folder(self.state_dir, group_id) / REMINDERS_FILE_NAME


def _pending_with_id(reminders: list[Reminder], reminder_id: str) -> Reminder | None:
    return next(
        (
            reminder
            for reminder in reminders
            if reminder.id == reminder_id.strip() and reminder.state is ReminderState.PENDING
        ),
        None,
    )


def _number_of(reminder_id: str) -> int:
    digits = reminder_id.removeprefix(REMINDER_ID_PREFIX)
    return int(digits) if digits.isdigit() else 0


def _last_number_of(document: dict[str, Any]) -> int:
    number = document.get("last_number", 0)
    return number if isinstance(number, int) and not isinstance(number, bool) else 0


def _reminders_of(document: dict[str, Any]) -> list[Reminder]:
    rows = document.get("reminders")
    if not isinstance(rows, list):
        return []
    return [found for row in rows if (found := _reminder_of(row)) is not None]


def _reminder_of(row: Any) -> Reminder | None:
    """Read one row; a row that is cut or of the wrong shape is left out."""
    if not isinstance(row, dict):
        return None
    try:
        names = row.get("names", [])
        attempts = row.get("attempts", 0)
        if (
            not isinstance(row["id"], str)
            or not isinstance(row["text"], str)
            or not isinstance(names, list)
            or not all(isinstance(name, str) for name in names)
            or isinstance(attempts, bool)
            or not isinstance(attempts, int)
        ):
            return None
        due_at = datetime.fromisoformat(row["due_at"])
        created_at = datetime.fromisoformat(row["created_at"])
        state = ReminderState(row["state"])
    except (KeyError, TypeError, ValueError):
        return None
    if due_at.tzinfo is None or created_at.tzinfo is None:
        return None
    return Reminder(row["id"], row["text"], due_at, tuple(names), created_at, state, attempts)


def _row_of(reminder: Reminder) -> dict[str, Any]:
    return {
        "id": reminder.id,
        "text": reminder.text,
        "due_at": reminder.due_at.isoformat(timespec="minutes"),
        "names": list(reminder.names),
        "created_at": reminder.created_at.isoformat(timespec="seconds"),
        "state": reminder.state.value,
        "attempts": reminder.attempts,
    }
