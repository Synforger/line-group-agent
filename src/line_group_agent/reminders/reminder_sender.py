"""Send the reminders whose time has come, one round at a time.

Called by the patrol every `ROUND_INTERVAL_SECONDS`. A reminder goes out as a push to its
group and is marked sent. A send that fails is tried once more at the next round, and when
that fails too the reminder is marked failed and logged. A reminder found more than
`LATE_LIMIT` after its time (the agent was not running) is not sent but marked missed.
The members a reminder calls are mentioned for real when the group's record knows their names;
LINE refusing that (a member who has left) sends the names as text. Rounds never overlap, so a
reminder is never sent twice. A sent reminder is not written into
the group's record: that record cuts "what was said since the bot's last turn" at the bot's
last message, so a reminder in it would hide what members said before it. Logs carry the
reminder's id and the status only.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Protocol

from line_group_agent.events.speaker_lookup import speakers_in
from line_group_agent.line_api.line_client import HTTP_BAD_REQUEST, LineApiError
from line_group_agent.records.group_log import GroupLog
from line_group_agent.reminders.push_left import PushLeft
from line_group_agent.reminders.reminder import Reminder, ReminderState
from line_group_agent.reminders.reminder_book import DueReminder, ReminderBook
from line_group_agent.reminders.reminder_text import reminder_text

logger = logging.getLogger(__name__)

ROUND_INTERVAL_SECONDS = 60
LATE_LIMIT = timedelta(minutes=30)
MAX_ATTEMPTS = 2


class ReminderLine(Protocol):
    """What the sender needs from the LINE client: a push to a group."""

    async def push(
        self, to: str, text: str | None, *, mentionable: Mapping[str, str] | None = None
    ) -> None: ...


class ReminderSender:
    """Sends the due reminders of every group."""

    def __init__(
        self,
        book: ReminderBook,
        line: ReminderLine,
        push_left: PushLeft,
        clock: Callable[[], datetime],
        *,
        group_log: GroupLog | None = None,
    ) -> None:
        self.book = book
        self.group_log = group_log
        self.line = line
        self.push_left = push_left
        self._clock = clock
        self._round_lock = asyncio.Lock()

    async def send_due(self) -> None:
        """Run one round: refresh the count of messages left, then send what is due."""
        async with self._round_lock:
            await self.push_left.refresh()
            now = self._clock()
            for due in self.book.due(now):
                await self._send_one(due, now)

    async def _send_one(self, due: DueReminder, now: datetime) -> None:
        group_id, reminder = due.group_id, due.reminder
        if reminder.attempts == 0 and now - reminder.due_at > LATE_LIMIT:
            self.book.finish(group_id, reminder.id, ReminderState.MISSED)
            logger.warning("reminder %s: not sent, it was more than 30 minutes late", reminder.id)
            return
        try:
            await self._push(group_id, reminder)
        except LineApiError as error:
            self._note_failure(group_id, reminder, error.status)
            return
        self.book.finish(group_id, reminder.id, ReminderState.SENT)

    async def _push(self, group_id: str, reminder: Reminder) -> None:
        """Push the reminder with its people called by real mentions where the group's record
        knows them; when LINE refuses that (a member who left the group), push it again with
        every name written as `@name`."""
        mentionable = self._mentionable(group_id, reminder)
        try:
            await self.line.push(
                group_id, reminder_text(reminder, mentionable), mentionable=mentionable
            )
        except LineApiError as error:
            if not mentionable or error.status != HTTP_BAD_REQUEST:
                raise
            logger.info("reminder %s: LINE refused the mentions; sending the names", reminder.id)
            await self.line.push(group_id, reminder_text(reminder))

    def _mentionable(self, group_id: str, reminder: Reminder) -> dict[str, str]:
        if self.group_log is None or not reminder.names:
            return {}
        speakers = speakers_in(self.group_log, group_id)
        return {name: speakers[name] for name in reminder.names if name in speakers}

    def _note_failure(self, group_id: str, reminder: Reminder, status: int) -> None:
        if reminder.attempts + 1 >= MAX_ATTEMPTS:
            self.book.finish(group_id, reminder.id, ReminderState.FAILED)
            logger.error(
                "reminder %s: given up after the send failed (status %d)", reminder.id, status
            )
            return
        self.book.note_failed_attempt(group_id, reminder.id)
        logger.warning(
            "reminder %s: the send failed (status %d); trying again", reminder.id, status
        )
