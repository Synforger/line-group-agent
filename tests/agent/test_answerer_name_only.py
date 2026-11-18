"""The answerer for a message that only holds the bot's name: the model may end the turn
with `stay_silent`; a message that calls the bot is always answered."""

import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.answerer import Answer
from line_group_agent.agent.prompt import (
    NAME_ONLY_NOTE,
    STAY_SILENT_REFUSED_RESULT,
    STAY_SILENT_RESULT,
    STAY_SILENT_SKIPPED_RESULT,
)
from line_group_agent.config.agent_config import DEFAULT_ERROR_TEXT
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


def message(number: int = 99, text: str = "昨日ソラに聞いたら便利だった") -> GroupMessage:
    return GroupMessage("2026-11-18T12:00:00+09:00", str(number), "U1", "Aki", text)


def silent_call(*extra: dict[str, Any]) -> dict[str, Any]:
    call = {"type": "tool_use", "id": "toolu_1", "name": "stay_silent", "input": {}}
    return answer([call, *extra], message_id="msg_1", stop_reason="tool_use")


def build(tmp_path: Path, answers: list[dict[str, Any]], **overrides: Any) -> World:
    return build_world(tmp_path, answers, call_name_anywhere=True, **overrides)


async def test_the_tool_is_offered_only_when_names_are_read_anywhere(tmp_path: Path) -> None:
    on = build(tmp_path / "on", [text_answer("<reply>ok</reply>")])
    off = build_world(tmp_path / "off", [text_answer("<reply>ok</reply>")])
    await on.answerer.answer(GROUP, message())
    await off.answerer.answer(GROUP, message())
    assert "stay_silent" in {t["name"] for t in on.client.messages.requests[0]["tools"]}
    assert "stay_silent" not in {t["name"] for t in off.client.messages.requests[0]["tools"]}


async def test_the_tool_list_is_the_same_for_every_turn(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("<reply>a</reply>"), text_answer("<reply>b</reply>")])
    await world.answerer.answer(GROUP, message(1), is_name_only=True)
    await world.answerer.answer(GROUP, message(2))
    first, second = world.client.messages.requests
    assert first["tools"] == second["tools"]


async def test_a_name_only_turn_tells_the_model_it_may_stay_silent(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("<reply>ok</reply>")])
    await world.answerer.answer(GROUP, message(), is_name_only=True)
    content = world.client.messages.requests[0]["messages"][0]["content"]
    assert NAME_ONLY_NOTE in content
    assert "The message that contains your name:" in content


async def test_a_call_turn_does_not_mention_staying_silent(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("<reply>ok</reply>")])
    await world.answerer.answer(GROUP, message())
    content = world.client.messages.requests[0]["messages"][0]["content"]
    assert "stay_silent" not in content
    assert "The message that mentioned you:" in content


async def test_stay_silent_sends_nothing_and_asks_the_model_no_more(tmp_path: Path) -> None:
    world = build(tmp_path, [silent_call(), text_answer("<reply>unused</reply>")])
    assert await world.answerer.answer(GROUP, message(), is_name_only=True) == Answer(None)
    assert len(world.client.messages.requests) == 1


async def test_a_silent_turn_stays_in_the_conversation_with_its_result(tmp_path: Path) -> None:
    world = build(tmp_path, [silent_call()])
    await world.answerer.answer(GROUP, message(7), is_name_only=True)
    conversation = world.conversations.get(GROUP)
    assert [m["role"] for m in conversation.messages] == ["user", "assistant", "user"]
    result = conversation.messages[2]["content"][0]
    assert result["tool_use_id"] == "toolu_1" and result["content"] == STAY_SILENT_RESULT
    assert conversation.last_turn_message_id == "7"


async def test_other_calls_of_a_silent_turn_are_not_run(tmp_path: Path) -> None:
    search = {
        "type": "tool_use",
        "id": "toolu_2",
        "name": "search_history",
        "input": {"query": "x"},
    }
    world = build(tmp_path, [silent_call(search)])
    await world.answerer.answer(GROUP, message(), is_name_only=True)
    results = world.conversations.get(GROUP).messages[2]["content"]
    assert [r["content"] for r in results] == [STAY_SILENT_RESULT, STAY_SILENT_SKIPPED_RESULT]
    assert results[1]["is_error"] is True


async def test_text_written_with_stay_silent_is_not_sent(tmp_path: Path) -> None:
    text = {"type": "text", "text": "<reply>hello</reply>"}
    world = build(tmp_path, [silent_call(text)])
    assert await world.answerer.answer(GROUP, message(), is_name_only=True) == Answer(None)


async def test_an_answer_without_stay_silent_is_sent_as_usual(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("<reply>Try Gion.</reply>")])
    assert (await world.answerer.answer(GROUP, message(), is_name_only=True)).text == "Try Gion."


async def test_a_name_only_turn_without_any_reply_gets_the_error_text(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("hmm")])
    assert await world.answerer.answer(GROUP, message(), is_name_only=True) == Answer(
        DEFAULT_ERROR_TEXT
    )


async def test_stay_silent_is_refused_for_a_message_that_calls_the_bot(tmp_path: Path) -> None:
    world = build(tmp_path, [silent_call(), text_answer("<reply>Try Gion.</reply>")])
    reply = await world.answerer.answer(GROUP, message())
    assert reply.text == "Try Gion."
    result = world.client.messages.requests[1]["messages"][2]["content"][0]
    assert result["content"] == STAY_SILENT_REFUSED_RESULT and result["is_error"] is True


async def test_the_next_turn_follows_a_silent_one_without_its_message_again(
    tmp_path: Path,
) -> None:
    world = build(tmp_path, [silent_call(), text_answer("<reply>Try Gion.</reply>")])
    first = message(1)
    world.group_log.add(GROUP, first)
    await world.answerer.answer(GROUP, first, is_name_only=True)
    second = message(2, "@bot 宿は?")
    world.group_log.add(GROUP, second)
    await world.answerer.answer(GROUP, second)
    request = world.client.messages.requests[1]["messages"]
    assert [m["role"] for m in request] == ["user", "assistant", "user", "user"]
    assert first.text not in json.dumps(request[3], ensure_ascii=False)
