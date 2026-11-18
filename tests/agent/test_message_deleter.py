import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.prompt import build_envelope
from line_group_agent.records.group_log import GroupMessage
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


def post(world: World, number: int, text: str, user: str | None = "U1") -> GroupMessage:
    message = GroupMessage(
        f"2026-11-18T12:{number:02d}:00+09:00",
        f"m{number}",
        user,
        "Aki",
        text,
        from_bot=user is None,
    )
    world.group_log.add(GROUP, message)
    return message


def conversation_with(world: World, messages: list[GroupMessage], mention: GroupMessage) -> None:
    conversation = world.conversations.get(GROUP)
    conversation.add_user(build_envelope(messages, mention))
    blocks = [
        {"type": "thinking", "thinking": "t", "signature": "s"},
        {"type": "text", "text": "<reply>ok</reply>"},
    ]
    conversation.add_assistant(
        {"id": "msg_1", "role": "assistant", "content": blocks, "usage": {"input_tokens": 50}}
    )


def record_text(world: World) -> str:
    return world.conversations.get(GROUP).log.path.read_text()


def test_deleting_removes_the_message_from_the_group_record_and_the_conversation(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [])
    secret, request = post(world, 1, "our secret plan"), post(world, 2, "@bot forget the plan")
    conversation_with(world, [secret], request)
    assert world.deleter.delete(GROUP, {"m1"}) == 1
    assert [m.message_id for m in world.group_log.list_recent(GROUP, 10)] == ["m2"]
    assert "secret" not in record_text(world) and "[deleted]" in record_text(world)
    assert "forget the plan" in record_text(world)


def test_the_conversation_is_marked_to_roll_over_and_loses_its_thinking_blocks(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [])
    secret, request = post(world, 1, "our secret plan"), post(world, 2, "@bot hi")
    conversation_with(world, [secret], request)
    world.deleter.delete(GROUP, {"m1"})
    conversation = world.conversations.get(GROUP)
    assert conversation.must_roll_over
    assert "thinking" not in record_text(world)
    assert conversation.messages[1]["content"] == [{"type": "text", "text": "<reply>ok</reply>"}]


def test_deleting_what_is_not_there_changes_nothing(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    conversation_with(world, [], post(world, 1, "@bot hi"))
    before = record_text(world)
    assert world.deleter.delete(GROUP, {"m9"}) == 0
    assert record_text(world) == before and not world.conversations.get(GROUP).must_roll_over


def test_with_no_running_conversation_nothing_is_marked(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    post(world, 1, "our secret plan")
    assert world.deleter.delete(GROUP, {"m1"}) == 1
    assert not world.conversations.get(GROUP).must_roll_over


def test_a_search_deletes_the_requesters_messages_and_the_bots_but_not_the_request(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [])
    post(world, 1, "kyoto idea", "U1")
    post(world, 2, "kyoto idea of someone else", "U2")
    post(world, 3, "bot kyoto answer", None)
    request = post(world, 4, "@bot delete kyoto", "U1")
    count = world.deleter.delete_matching(
        GROUP, "kyoto", requester_user_id="U1", request_message_id=request.message_id
    )
    assert count == 2
    assert [m.message_id for m in world.group_log.list_recent(GROUP, 10)] == ["m2", "m4"]


def test_a_search_deletes_at_most_the_search_limit(tmp_path: Path) -> None:
    world = build_world(tmp_path, [], history_search_limit=2)
    for number in range(1, 6):
        post(world, number, f"kyoto {number}")
    request = post(world, 6, "@bot delete kyoto")
    count = world.deleter.delete_matching(
        GROUP, "kyoto", requester_user_id="U1", request_message_id=request.message_id
    )
    assert count == 2
    assert [m.message_id for m in world.group_log.list_recent(GROUP, 10)] == [
        "m1",
        "m2",
        "m3",
        "m6",
    ]


async def test_an_unsent_message_is_deleted_under_the_conversations_lock(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    secret, request = post(world, 1, "our secret plan"), post(world, 2, "@bot hi")
    conversation_with(world, [secret], request)
    assert await world.deleter.delete_unsent(GROUP, "m1") == 1
    assert await world.deleter.delete_unsent(GROUP, "m1") == 0
    assert not world.conversations.get(GROUP).lock.locked()


def test_the_record_file_is_replaced_whole_without_a_temporary_file(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    secret, request = post(world, 1, "our secret plan"), post(world, 2, "@bot hi")
    conversation_with(world, [secret], request)
    world.deleter.delete(GROUP, {"m1"})
    folder = world.conversations.get(GROUP).log.path.parent
    assert [p.name for p in folder.iterdir()] == ["g-callowed.jsonl"]
    rows: list[dict[str, Any]] = [json.loads(line) for line in record_text(world).splitlines()]
    assert [r["type"] for r in rows] == ["user", "assistant"]
