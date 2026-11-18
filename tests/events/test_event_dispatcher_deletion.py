"""A message a member takes back (unsend) is deleted from the records, and the
conversation is rolled over at once."""

import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.prompt import summary_request
from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.records.group_log import GroupMessage
from tests.events.test_event_dispatcher import OTHER, ScriptedAnswerer, text_event
from tests.fakes import text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


def unsend_event(message_id: str, group_id: str = GROUP) -> dict[str, Any]:
    return {
        "type": "unsend",
        "source": {"type": "group", "groupId": group_id, "userId": "U1"},
        "unsend": {"messageId": message_id},
    }


def dispatcher_of(world: World) -> EventDispatcher:
    return EventDispatcher(
        frozenset({GROUP}),
        world.line,
        world.group_log,
        ScriptedAnswerer(),
        observer=world.watcher,
        deleter=world.deleter,
    )


def usage() -> dict[str, Any]:
    return {"input_tokens": 100, "output_tokens": 10}


async def test_an_unsent_message_is_deleted_from_the_record_and_the_conversation(
    tmp_path: Path,
) -> None:
    summary = text_answer("Decided nothing.", message_id="msg_s", usage=usage())
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>", usage=usage()), summary])
    dispatcher = dispatcher_of(world)
    await dispatcher.handle(text_event(GROUP, "our secret plan", message_id="m1"))
    await world.answerer.answer(GROUP, world.group_log.list_recent(GROUP, 1)[0])

    await dispatcher.handle(unsend_event("m1"))

    assert world.group_log.list_recent(GROUP, 10) == []
    conversation = world.conversations.get(GROUP)
    assert "secret" not in conversation.log.path.read_text()
    assert conversation.pending_summary == "Decided nothing."
    request = world.client.messages.requests[-1]
    assert request["messages"][-1]["content"] == summary_request(after_deletion=True)
    assert "secret" not in json.dumps(request["messages"])


async def test_an_unsent_message_that_was_never_recorded_changes_nothing(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    dispatcher = dispatcher_of(world)
    await dispatcher.handle(text_event(GROUP, "hello", message_id="m1"))
    await dispatcher.handle(unsend_event("m9"))
    assert [m.message_id for m in world.group_log.list_recent(GROUP, 10)] == ["m1"]
    assert world.client.messages.requests == []


async def test_an_unsend_from_a_group_that_is_not_allowed_is_dropped(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    dispatcher = dispatcher_of(world)
    world.group_log.add(OTHER, GroupMessage("t", "m1", "U1", "A", "x"))
    await dispatcher.handle(unsend_event("m1", OTHER))
    assert [m.message_id for m in world.group_log.list_recent(OTHER, 10)] == ["m1"]


async def test_without_a_deleter_an_unsend_is_ignored(tmp_path: Path) -> None:
    world = build_world(tmp_path, [])
    dispatcher = dispatcher_of(world)
    dispatcher.deleter = None
    await dispatcher.handle(text_event(GROUP, "hello", message_id="m1"))
    await dispatcher.handle(unsend_event("m1"))
    assert len(world.group_log.list_recent(GROUP, 10)) == 1
