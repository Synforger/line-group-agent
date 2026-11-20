import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from line_group_agent.line_api.push_quota import PushQuota
from line_group_agent.reminders.push_left import PushLeft
from line_group_agent.reminders.reminder import GROUP_TIME_ZONE, Reminder, ReminderState
from line_group_agent.reminders.reminder_book import REMINDERS_FILE_NAME, ReminderBook
from line_group_agent.reminders.reminder_sender import ReminderSender
from tests.fakes import FakeLine
from tests.world import GROUP, Clock

pytestmark = pytest.mark.anyio
DUE = datetime(2026, 11, 20, 21, 0, tzinfo=GROUP_TIME_ZONE)


class Setup:
    def __init__(self, tmp_path: Path, **line_options: object) -> None:
        self.state_dir = tmp_path
        self.clock = Clock(DUE - timedelta(hours=1))
        self.book = ReminderBook(tmp_path, self.clock)
        self.line = FakeLine(**line_options)  # type: ignore[arg-type]
        self.push_left = PushLeft(PushQuota(self.line))
        self.sender = ReminderSender(self.book, self.line, self.push_left, self.clock)

    def state_of(self, reminder_id: str, group: str = GROUP) -> ReminderState:
        path = self.state_dir / "groups" / group / REMINDERS_FILE_NAME
        rows = json.loads(path.read_text(encoding="utf-8"))["reminders"]
        return ReminderState(next(row["state"] for row in rows if row["id"] == reminder_id))


async def test_nothing_is_sent_before_the_time(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "Gather", DUE, ())
    await setup.sender.send_due()
    assert setup.line.pushes == []
    assert [r.id for r in setup.book.list_pending(GROUP)] == ["r1"]


async def test_a_reminder_is_pushed_as_it_is_at_its_time_and_marked_sent(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "Gather at 21:00", DUE, ())
    setup.clock.moment = DUE
    await setup.sender.send_due()
    assert setup.line.pushes == [(GROUP, "Gather at 21:00")]
    assert setup.state_of("r1") is ReminderState.SENT
    await setup.sender.send_due()
    assert len(setup.line.pushes) == 1


async def test_the_people_to_call_are_named_before_the_text(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "Gather", DUE, ("Aki", "Ben"))
    setup.clock.moment = DUE
    await setup.sender.send_due()
    assert setup.line.pushes == [(GROUP, "@Aki @Ben Gather")]


async def test_a_failed_send_is_tried_again_once_at_the_next_round_and_then_sent(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path, push_statuses=[500, None])
    setup.book.add(GROUP, "Gather", DUE, ())
    setup.clock.moment = DUE
    await setup.sender.send_due()
    assert setup.state_of("r1") is ReminderState.PENDING
    setup.clock.advance(minutes=1)
    await setup.sender.send_due()
    assert setup.state_of("r1") is ReminderState.SENT
    assert len(setup.line.pushes) == 2


async def test_a_reminder_whose_send_fails_twice_is_given_up_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    setup = Setup(tmp_path, push_statuses=[500, 429, None])
    setup.book.add(GROUP, "Gather", DUE, ())
    setup.clock.moment = DUE
    with caplog.at_level(logging.ERROR):
        await setup.sender.send_due()
        setup.clock.advance(minutes=1)
        await setup.sender.send_due()
    assert setup.state_of("r1") is ReminderState.FAILED
    assert "reminder r1: given up" in caplog.text and "Gather" not in caplog.text
    setup.clock.advance(minutes=1)
    await setup.sender.send_due()
    assert len(setup.line.pushes) == 2


async def test_a_retry_still_goes_out_even_when_it_falls_past_the_late_limit(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path, push_statuses=[500, None])
    setup.book.add(GROUP, "Gather", DUE, ())
    setup.clock.moment = DUE + timedelta(minutes=29, seconds=30)
    await setup.sender.send_due()
    setup.clock.advance(minutes=1)
    await setup.sender.send_due()
    assert setup.state_of("r1") is ReminderState.SENT


async def test_a_reminder_up_to_thirty_minutes_late_is_sent(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "Gather", DUE, ())
    setup.clock.moment = DUE + timedelta(minutes=30)
    await setup.sender.send_due()
    assert setup.line.pushes == [(GROUP, "Gather")]


async def test_a_reminder_more_than_thirty_minutes_late_is_not_sent_but_marked_missed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "Gather", DUE, ())
    setup.clock.moment = DUE + timedelta(minutes=30, seconds=1)
    with caplog.at_level(logging.WARNING):
        await setup.sender.send_due()
    assert setup.line.pushes == [] and setup.state_of("r1") is ReminderState.MISSED
    assert "reminder r1: not sent" in caplog.text


async def test_the_due_reminders_of_every_group_go_out_in_time_order(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "second", DUE, ())
    setup.book.add("Cother", "first", DUE - timedelta(minutes=5), ())
    setup.clock.moment = DUE + timedelta(minutes=1)
    await setup.sender.send_due()
    assert setup.line.pushes == [("Cother", "first"), (GROUP, "second")]


async def test_a_round_refreshes_the_messages_left(tmp_path: Path) -> None:
    setup = Setup(tmp_path, remaining_messages=42)
    assert setup.push_left.get() is None
    await setup.sender.send_due()
    assert setup.push_left.get() == 42


async def test_two_rounds_at_once_never_send_a_reminder_twice(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.book.add(GROUP, "Gather", DUE, ())
    setup.clock.moment = DUE
    await asyncio.gather(setup.sender.send_due(), setup.sender.send_due())
    assert len(setup.line.pushes) == 1


def test_a_reminder_is_a_plain_value() -> None:
    reminder = Reminder("r1", "x", DUE, (), DUE)
    assert reminder.state is ReminderState.PENDING and reminder.attempts == 0
