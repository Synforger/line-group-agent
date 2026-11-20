"""The answerer when the model's last answer has text but no `<reply>`: the model is asked once,
inside the same turn, to write the answer again inside `<reply>`."""

from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.answerer import Answer
from line_group_agent.agent.prompt import REPLY_RETRY_REQUEST
from line_group_agent.config.agent_config import DEFAULT_ERROR_TEXT
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


def message(number: int = 99) -> GroupMessage:
    return GroupMessage("2026-11-18T12:00:00+09:00", str(number), "U1", "Aki", "@bot 宿は?")


def build(tmp_path: Path, answers: list[dict[str, Any]], **overrides: Any) -> World:
    return build_world(tmp_path, answers, call_name_anywhere=True, **overrides)


async def test_an_answer_without_reply_is_asked_for_again_and_the_new_reply_is_sent(
    tmp_path: Path,
) -> None:
    world = build(tmp_path, [text_answer("Try Gion."), text_answer("<reply>Try Gion.</reply>")])
    assert await world.answerer.answer(GROUP, message()) == Answer("Try Gion.")
    assert len(world.client.messages.requests) == 2


async def test_the_request_continues_the_same_turn(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("Try Gion."), text_answer("<reply>Try Gion.</reply>")])
    await world.answerer.answer(GROUP, message())
    request = world.client.messages.requests[1]["messages"]
    assert [m["role"] for m in request] == ["user", "assistant", "user"]
    assert request[1]["content"][0]["text"] == "Try Gion."
    assert request[2]["content"] == REPLY_RETRY_REQUEST
    assert "<reply></reply>" in REPLY_RETRY_REQUEST


async def test_the_request_and_its_answer_stay_in_the_conversation(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("Try Gion."), text_answer("<reply>Try Gion.</reply>")])
    await world.answerer.answer(GROUP, message())
    recorded = world.conversations.get(GROUP).messages
    assert [m["role"] for m in recorded] == ["user", "assistant", "user", "assistant"]
    assert recorded[2]["content"] == REPLY_RETRY_REQUEST


async def test_it_is_asked_only_once(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("a"), text_answer("b"), text_answer("<reply>c</reply>")])
    assert await world.answerer.answer(GROUP, message()) == Answer(DEFAULT_ERROR_TEXT)
    assert len(world.client.messages.requests) == 2


async def test_a_called_turn_that_is_still_without_reply_gets_the_error_text(
    tmp_path: Path,
) -> None:
    world = build(tmp_path, [text_answer("a"), text_answer("b")])
    assert (await world.answerer.answer(GROUP, message())).text == DEFAULT_ERROR_TEXT


async def test_a_name_only_turn_that_is_still_without_reply_is_silent(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("a"), text_answer("b")])
    assert await world.answerer.answer(GROUP, message(), is_name_only=True) == Answer(None)
    assert len(world.client.messages.requests) == 2


async def test_a_name_only_turn_is_asked_again_too(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("Try Gion."), text_answer("<reply>Try Gion.</reply>")])
    result = await world.answerer.answer(GROUP, message(), is_name_only=True)
    assert result.text == "Try Gion."


async def test_an_answer_with_a_reply_is_not_asked_again(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("<reply>ok</reply>"), text_answer("<reply>x</reply>")])
    await world.answerer.answer(GROUP, message())
    assert len(world.client.messages.requests) == 1


async def test_an_empty_reply_is_a_reply_and_is_not_asked_again(tmp_path: Path) -> None:
    world = build(tmp_path, [text_answer("<reply></reply>"), text_answer("<reply>x</reply>")])
    assert await world.answerer.answer(GROUP, message()) == Answer(DEFAULT_ERROR_TEXT)
    assert len(world.client.messages.requests) == 1


async def test_an_answer_without_text_is_not_asked_again_and_stays_silent(tmp_path: Path) -> None:
    world = build(tmp_path, [answer([]), text_answer("<reply>x</reply>")])
    assert await world.answerer.answer(GROUP, message()) == Answer(None)
    assert len(world.client.messages.requests) == 1


async def test_a_reply_written_in_an_earlier_round_is_not_asked_for_again(tmp_path: Path) -> None:
    search = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "search_history",
        "input": {"query": "x"},
    }
    first = answer(
        [{"type": "text", "text": "<reply>Looking.</reply>"}, search], stop_reason="tool_use"
    )
    world = build(tmp_path, [first, text_answer("Done.")])
    assert (await world.answerer.answer(GROUP, message())).text == "Looking."
    assert len(world.client.messages.requests) == 2


async def test_it_is_not_asked_when_the_budget_cannot_take_another_request(
    tmp_path: Path,
) -> None:
    expensive = {"input_tokens": 20_000_000, "output_tokens": 0}
    world = build(
        tmp_path, [text_answer("Try Gion.", usage=expensive), text_answer("<reply>x</reply>")]
    )
    result = await world.answerer.answer(GROUP, message())
    assert result == Answer("This month's budget is used up.")
    assert len(world.client.messages.requests) == 1


async def test_cards_are_sent_with_the_reply_that_was_asked_for(tmp_path: Path) -> None:
    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "show_cards",
        "input": {"cards": [{"title": "Gion Inn", "text": "x", "url": "https://example.com/g"}]},
    }
    world = build(
        tmp_path,
        [
            answer([call], stop_reason="tool_use"),
            text_answer("Here you go."),
            text_answer("<reply>Here you go.</reply>"),
        ],
    )
    result = await world.answerer.answer(GROUP, message())
    assert result.text == "Here you go." and len(result.cards) == 1
