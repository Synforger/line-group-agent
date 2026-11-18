from pathlib import Path

import pytest

from line_group_agent.records.group_log import GroupMessage
from tests.world import GROUP, build_world

pytestmark = pytest.mark.anyio


def message(time: str = "2026-11-18T12:30:00+09:00") -> GroupMessage:
    return GroupMessage(time, "m1", "U1", "Aki", "hello")


async def test_a_message_registers_the_group_and_notes_when_it_spoke(tmp_path: Path) -> None:
    world = build_world(tmp_path, [], allowed_group_ids=[])
    await world.watcher.note_message("Cnew", message())
    conversation = world.conversations.get("Cnew")
    assert conversation.last_activity_at is not None and conversation.last_activity_at.minute == 30
    assert [t["name"] for t in world.tabs_json()["tabs"]] == ["g-cnew"]


async def test_the_group_name_is_looked_up_once_an_hour_and_kept_when_line_gives_none(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [])
    await world.watcher.note_message(GROUP, message())
    await world.watcher.note_message(GROUP, message())
    assert world.line.group_name_lookups == 1
    world.line.group_names[GROUP] = "Renamed"
    world.clock.advance(minutes=59)
    await world.watcher.patrol()
    assert world.line.group_name_lookups == 1
    world.clock.advance(minutes=2)
    await world.watcher.patrol()
    assert world.conversations.get(GROUP).title == "Renamed"
    del world.line.group_names[GROUP]
    world.clock.advance(hours=2)
    await world.watcher.patrol()
    assert world.conversations.get(GROUP).title == "Renamed"


async def test_a_group_whose_name_is_unknown_is_asked_again_at_the_next_hour(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [])
    world.line.group_names.clear()
    await world.watcher.note_message(GROUP, message())
    assert world.conversations.get(GROUP).title is None
    assert world.tabs_json()["tabs"][0]["title"] == "g-callowed"


async def test_the_patrol_rereads_the_settings_and_rewrites_the_tab_list(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    await world.watcher.patrol()
    world.write_settings(context_window_tokens=30_000)
    await world.watcher.patrol()
    assert world.tabs_json()["context_window"] == 30_000
