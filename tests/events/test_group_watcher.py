from pathlib import Path

import pytest

from line_group_agent.records.group_log import GroupMessage
from tests.fakes import text_answer
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


async def test_after_a_deletion_a_marked_conversation_is_summarized_at_once(
    tmp_path: Path,
) -> None:
    usage = {"input_tokens": 10, "output_tokens": 1}
    summary = text_answer("Summary.", message_id="msg_s", usage=usage)
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>", usage=usage), summary])
    secret = GroupMessage("2026-11-18T12:00:00+09:00", "m1", "U1", "Aki", "a secret")
    world.group_log.add(GROUP, secret)
    await world.answerer.answer(GROUP, GroupMessage("t", "m2", "U1", "Aki", "@bot hi"))
    world.deleter.delete(GROUP, {"m1"})
    await world.watcher.after_deletion(GROUP)
    conversation = world.conversations.get(GROUP)
    assert conversation.pending_summary == "Summary."
    assert world.tabs_json()["tabs"][0]["generation"] == 2


async def test_the_patrol_sweeps_expired_messages_once_a_day(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.group_log.add(GROUP, GroupMessage("2026-09-01T12:00:00+09:00", "m1", "U1", "A", "old"))
    world.group_log.add(GROUP, GroupMessage("2026-11-17T12:00:00+09:00", "m2", "U1", "A", "new"))
    await world.watcher.patrol()
    assert [m.text for m in world.group_log.list_recent(GROUP, 10)] == ["new"]


async def test_a_watcher_without_a_sweeper_keeps_everything(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    world.watcher.retention = None
    world.group_log.add(GROUP, GroupMessage("2026-09-01T12:00:00+09:00", "m1", "U1", "A", "old"))
    await world.watcher.patrol()
    assert len(world.group_log.list_recent(GROUP, 10)) == 1
