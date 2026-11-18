import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.records.retention_sweeper import RetentionSweeper
from line_group_agent.records.summary_journal import SummaryJournal

pytestmark = pytest.mark.anyio
TOKYO = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=TOKYO)


class Clock:
    def __init__(self) -> None:
        self.moment = NOW

    def __call__(self) -> datetime:
        return self.moment


def row(kind: str, timestamp: str, content: Any) -> str:
    message = {"role": "user", "content": content} if kind == "user" else content
    return json.dumps({"type": kind, "uuid": "u", "timestamp": timestamp, "message": message})


def setup(
    tmp_path: Path, days: int = 30
) -> tuple[RetentionSweeper, GroupLog, GroupConversations, Clock]:
    group_log = GroupLog(tmp_path)
    journal = SummaryJournal(tmp_path)
    conversations = GroupConversations(tmp_path, group_log, journal)
    clock = Clock()
    return RetentionSweeper(conversations, group_log, days, clock), group_log, conversations, clock


def said(group_log: GroupLog, number: int, time: str) -> None:
    group_log.add("Ca", GroupMessage(time, f"m{number}", "U1", "Aki", f"text {number}"))


async def test_old_messages_and_old_rows_go_and_the_running_generation_and_journal_stay(
    tmp_path: Path,
) -> None:
    sweeper, group_log, conversations, _ = setup(tmp_path)
    said(group_log, 1, "2026-09-01T12:00:00+09:00")
    said(group_log, 2, "2026-10-01T12:00:00+09:00")
    said(group_log, 3, "2026-11-10T12:00:00+09:00")
    record = tmp_path / "conversations" / "g-ca.jsonl"
    record.parent.mkdir(parents=True)
    answer = {"id": "m", "role": "assistant", "content": [], "usage": {"input_tokens": 5}}
    record.write_text(
        "\n".join(
            [
                row("user", "2026-09-01T03:00:00.000Z", "old turn"),
                row("assistant", "2026-09-01T03:00:05.000Z", answer),
                row(
                    "user",
                    "2026-10-01T03:00:00.000Z",
                    "Summary of the conversation so far\ns\n\nlive",
                ),
                row("assistant", "2026-10-01T03:00:05.000Z", answer),
            ]
        )
        + "\n"
    )
    SummaryJournal(tmp_path).write("Ca", 1, "s", date(2026, 10, 1))
    conversations.open([])

    assert await sweeper.sweep_if_due() == 2 + 1
    assert [m.text for m in group_log.list_recent("Ca", 10)] == ["text 2", "text 3"]
    assert len(conversations.get("Ca").log.read_rows()) == 2
    assert (tmp_path / "groups" / "Ca" / "journal" / "2026-10-01-gen1.md").exists()


async def test_the_sweep_runs_once_a_day(tmp_path: Path) -> None:
    sweeper, group_log, conversations, clock = setup(tmp_path)
    conversations.open(["Ca"])
    assert await sweeper.sweep_if_due() == 0
    said(group_log, 1, "2026-09-01T12:00:00+09:00")
    clock.moment += timedelta(hours=23)
    assert await sweeper.sweep_if_due() == 0
    assert len(group_log.list_recent("Ca", 10)) == 1
    clock.moment += timedelta(hours=1)
    assert await sweeper.sweep_if_due() == 1


async def test_the_period_is_configurable(tmp_path: Path) -> None:
    sweeper, group_log, conversations, _ = setup(tmp_path, days=7)
    said(group_log, 1, "2026-11-10T12:00:00+09:00")
    said(group_log, 2, "2026-11-15T12:00:00+09:00")
    conversations.open([])
    await sweeper.sweep_if_due()
    assert [m.text for m in group_log.list_recent("Ca", 10)] == ["text 2"]
