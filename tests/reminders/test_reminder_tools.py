from datetime import datetime, timedelta
from pathlib import Path

import pytest

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.line_api.push_quota import PushQuota
from line_group_agent.records.group_log import GroupMessage
from line_group_agent.reminders.push_left import PushLeft
from line_group_agent.reminders.reminder import GROUP_TIME_ZONE
from line_group_agent.reminders.reminder_book import ReminderBook
from line_group_agent.reminders.reminder_tools import reminder_tools
from tests.fakes import FakeLine
from tests.world import GROUP, NOW_FOR_TESTS, Clock

MENTION = GroupMessage("t", "99", "U1", "Aki", "@bot remind us")
TOMORROW_EVENING = "2026-11-19T21:00"


class Setup:
    def __init__(self, tmp_path: Path, *, max_per_month: int = 10, min_push_left: int = 20) -> None:
        self.clock = Clock(NOW_FOR_TESTS)
        self.book = ReminderBook(tmp_path, self.clock)
        self.line = FakeLine(remaining_messages=1000)
        self.push_left = PushLeft(PushQuota(self.line))
        self.tools: dict[str, ClientTool] = {
            tool.name: tool
            for tool in reminder_tools(
                self.book,
                self.push_left,
                max_per_month=max_per_month,
                min_push_left=min_push_left,
                clock=self.clock,
            )
        }

    def call(self, name: str, tool_input: object, group: str = GROUP) -> ToolOutcome:
        return self.tools[name].run(tool_input, ToolTurn(group, MENTION, TurnOutput()))


def test_set_reminder_keeps_the_reminder_and_says_when_in_japan_time(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    outcome = setup.call(
        "set_reminder", {"when": TOMORROW_EVENING, "text": "Gather at 21:00", "who": ["Aki"]}
    )
    assert not outcome.is_error
    assert outcome.content == "Set r1: 2026-11-19 (Thu) 21:00 calling Aki: Gather at 21:00"
    [kept] = setup.book.list_pending(GROUP)
    assert kept.due_at == datetime(2026, 11, 19, 21, 0, tzinfo=GROUP_TIME_ZONE)
    assert kept.names == ("Aki",)


@pytest.mark.parametrize(
    ("tool_input", "message"),
    [
        (None, "ISO date and time"),
        ({"text": "x"}, "ISO date and time"),
        ({"when": "2026-11-18T11:00", "text": "x"}, "already passed"),
        ({"when": "2027-03-01T10:00", "text": "x"}, "60 days"),
        ({"when": TOMORROW_EVENING}, "text is required"),
        ({"when": TOMORROW_EVENING, "text": "x", "who": "Aki"}, "list of display names"),
    ],
)
def test_set_reminder_refuses_a_bad_call_and_keeps_nothing(
    tmp_path: Path, tool_input: object, message: str
) -> None:
    setup = Setup(tmp_path)
    outcome = setup.call("set_reminder", tool_input)
    assert outcome.is_error and message in outcome.content and "Nothing was set" in outcome.content
    assert setup.book.list_pending(GROUP) == []


def test_set_reminder_refuses_past_the_monthly_count_but_not_in_another_month(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path, max_per_month=2)
    for hour in (9, 10):
        assert not setup.call(
            "set_reminder", {"when": f"2026-11-19T{hour:02d}:00", "text": "x"}
        ).is_error
    refused = setup.call("set_reminder", {"when": "2026-11-20T09:00", "text": "x"})
    assert refused.is_error and "2 reminders in 2026-11" in refused.content
    assert not setup.call("set_reminder", {"when": "2026-12-01T09:00", "text": "x"}).is_error


def test_cancelling_frees_a_place_in_the_month(tmp_path: Path) -> None:
    setup = Setup(tmp_path, max_per_month=1)
    setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "x"})
    setup.call("cancel_reminder", {"id": "r1"})
    assert not setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "y"}).is_error


def test_the_monthly_count_is_per_group(tmp_path: Path) -> None:
    setup = Setup(tmp_path, max_per_month=1)
    setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "x"})
    assert not setup.call(
        "set_reminder", {"when": TOMORROW_EVENING, "text": "x"}, "Cother"
    ).is_error


@pytest.mark.anyio
async def test_set_reminder_is_refused_when_few_messages_are_left(tmp_path: Path) -> None:
    setup = Setup(tmp_path, min_push_left=20)
    setup.line.remaining_messages = 19
    await setup.push_left.refresh()
    outcome = setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "x"})
    assert outcome.is_error and "only 19 messages left" in outcome.content
    assert setup.book.list_pending(GROUP) == []


@pytest.mark.anyio
async def test_set_reminder_is_taken_at_exactly_the_least_messages_left(tmp_path: Path) -> None:
    setup = Setup(tmp_path, min_push_left=20)
    setup.line.remaining_messages = 20
    await setup.push_left.refresh()
    assert not setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "x"}).is_error


def test_set_reminder_is_taken_while_the_messages_left_are_not_known(tmp_path: Path) -> None:
    setup = Setup(tmp_path, min_push_left=20)
    assert not setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "x"}).is_error


def test_list_reminders_gives_the_time_now_the_count_and_the_waiting_ones(tmp_path: Path) -> None:
    setup = Setup(tmp_path, max_per_month=10)
    empty = setup.call("list_reminders", {})
    assert "It is 2026-11-18 (Wed) 12:00 now" in empty.content
    assert (
        "0 of 10 reminders of 2026-11" in empty.content
        and "No reminder is waiting" in empty.content
    )
    setup.call("set_reminder", {"when": "2026-11-20T09:00", "text": "second"})
    setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "first", "who": ["Aki", "Ben"]})
    listed = setup.call("list_reminders", None).content.splitlines()
    assert listed[1] == "r2: 2026-11-19 (Thu) 21:00 calling Aki, Ben: first"
    assert listed[2] == "r1: 2026-11-20 (Fri) 09:00: second"


def test_cancel_reminder_removes_it_and_refuses_an_unknown_id(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.call("set_reminder", {"when": TOMORROW_EVENING, "text": "x"})
    outcome = setup.call("cancel_reminder", {"id": "r1"})
    assert outcome.content.startswith("Cancelled r1:") and not outcome.is_error
    for tool_input in ({"id": "r1"}, {"id": 3}, {}, None):
        refused = setup.call("cancel_reminder", tool_input)
        assert refused.is_error and "list_reminders" in refused.content


def test_the_tool_definitions_name_the_required_fields(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    assert setup.tools["set_reminder"].definition["input_schema"]["required"] == ["when", "text"]
    assert setup.tools["cancel_reminder"].definition["input_schema"]["required"] == ["id"]
    assert set(setup.tools) == {"set_reminder", "list_reminders", "cancel_reminder"}


def test_a_reminder_is_kept_even_a_minute_ahead(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    soon = (NOW_FOR_TESTS + timedelta(minutes=1)).isoformat()
    assert not setup.call("set_reminder", {"when": soon, "text": "x"}).is_error
