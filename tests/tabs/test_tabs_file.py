import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.tabs.settings_fields import SETTINGS_FIELDS
from tests.fakes import text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


async def say(world: World, number: int, text: str) -> Any:
    from line_group_agent.records.group_log import GroupMessage

    message = GroupMessage(f"2026-11-18T12:{number:02d}:00+09:00", f"m{number}", "U1", "Aki", text)
    world.group_log.add(GROUP, message)
    await world.watcher.note_message(GROUP, message)
    return message


def usage(tokens: int) -> dict[str, int]:
    return {"input_tokens": tokens, "output_tokens": 10}


async def test_the_file_has_the_agreed_shape(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.tabs.refresh()
    document = world.tabs_json()
    assert set(document) == {"updated_at", "settings_fields", "context_window", "tabs"}
    assert document["context_window"] == 100_000
    [tab] = document["tabs"]
    assert tab == {
        "name": "g-callowed",
        "title": "g-callowed",
        "record": str(tmp_path / "state" / "conversations" / "g-callowed.jsonl"),
        "context_tokens": 0,
        "spend": {"month": "2026-11", "spent": 0.0, "limit": 1000.0, "currency": "JPY"},
        "generation": 1,
        "last_rollover_at": None,
    }


async def test_the_settings_fields_are_listed_at_the_top(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.tabs.refresh()
    document = world.tabs_json()
    assert list(document)[:2] == ["updated_at", "settings_fields"]
    fields = document["settings_fields"]
    assert [f["key"] for f in fields] == [
        "monthly_budget_usd",
        "context_window_tokens",
        "rollover_percent",
        "idle_rollover_percent",
        "idle_hours",
    ]
    for field in fields:
        assert set(field) == {"key", "label", "unit", "min", "max", "step", "default"}
        assert field["min"] <= field["default"] <= field["max"]
    assert fields == SETTINGS_FIELDS
    assert fields[0]["default"] == 100 and fields[2]["default"] == 60


async def test_the_title_is_the_group_name_from_line(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    await say(world, 1, "hello")
    assert world.tabs_json()["tabs"][0]["title"] == "Trip friends"


async def test_a_group_that_speaks_gets_a_tab_and_shares_the_budget(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.conversations.get("Cnew")
    world.tabs.refresh()
    tabs = world.tabs_json()["tabs"]
    assert [t["name"] for t in tabs] == ["g-callowed", "g-cnew"]
    assert {t["spend"]["limit"] for t in tabs} == {500.0}


async def test_the_context_amount_is_the_number_the_rollover_decision_uses(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer("<reply>a</reply>", usage=usage(61_000))])
    message = await say(world, 1, "@bot hi")
    await world.answerer.answer(GROUP, message)
    await world.watcher.after_answer(GROUP)
    tab = world.tabs_json()["tabs"][0]
    assert tab["context_tokens"] == 61_000
    assert tab["spend"]["spent"] > 0


async def test_after_a_rollover_the_context_is_zero_and_the_generation_is_the_next(
    tmp_path: Path,
) -> None:
    answers = [
        text_answer("<reply>a</reply>", usage=usage(61_000)),
        text_answer("Summary text", message_id="msg_2", usage=usage(61_500)),
    ]
    world = build_world(tmp_path, answers)
    message = await say(world, 1, "@bot hi")
    await world.answerer.answer(GROUP, message)
    await world.watcher.after_answer(GROUP)
    tab = world.tabs_json()["tabs"][0]
    assert tab["context_tokens"] == 0
    assert tab["generation"] == 2
    assert tab["last_rollover_at"] == world.clock().isoformat(timespec="seconds")


async def test_the_file_is_written_only_when_something_shown_changed(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.tabs.refresh()
    first = world.tabs_json()["updated_at"]
    world.clock.advance(minutes=5)
    world.tabs.refresh()
    assert world.tabs_json()["updated_at"] == first
    world.write_settings(context_window_tokens=50_000)
    world.tabs.refresh()
    document = world.tabs_json()
    assert document["context_window"] == 50_000 and document["updated_at"] != first


async def test_a_changed_budget_changes_every_groups_limit(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.write_settings(monthly_budget_usd=10)
    world.tabs.refresh()
    assert world.tabs_json()["tabs"][0]["spend"]["limit"] == 1500.0


async def test_the_file_is_replaced_whole_and_leaves_no_temporary(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.tabs.refresh()
    assert json.loads(world.config.tabs_file.read_text())
    assert not [p for p in world.config.tabs_file.parent.iterdir() if p.suffix == ".tmp"]
