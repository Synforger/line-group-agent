"""Thinking blocks of earlier turns are not sent again: their signature is tied to the
system text and the tool list that made them."""

import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.thinking_blocks import without_thinking
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio
THINKING = {"type": "thinking", "thinking": "hm", "signature": "sig=="}
REDACTED = {"type": "redacted_thinking", "data": "xyz"}
TEXT = {"type": "text", "text": "<reply>ok</reply>"}


def said(world: World, number: int, text: str) -> GroupMessage:
    message = GroupMessage(f"2026-11-18T12:{number:02d}:00+09:00", f"m{number}", "U1", "Aki", text)
    world.group_log.add(GROUP, message)
    return message


def test_thinking_and_redacted_thinking_are_taken_out_of_assistant_messages() -> None:
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [THINKING, REDACTED, TEXT]},
    ]
    assert without_thinking(messages)[1] == {"role": "assistant", "content": [TEXT]}


def test_the_input_is_not_changed() -> None:
    messages = [{"role": "assistant", "content": [THINKING, TEXT]}]
    without_thinking(messages)
    assert messages == [{"role": "assistant", "content": [THINKING, TEXT]}]


def test_a_conversation_without_thinking_comes_back_equal() -> None:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [TEXT]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "r"}]},
    ]
    assert without_thinking(messages) == messages


def test_an_assistant_message_of_nothing_but_thinking_is_left_out() -> None:
    messages = [{"role": "user", "content": "q"}, {"role": "assistant", "content": [THINKING]}]
    assert without_thinking(messages) == [{"role": "user", "content": "q"}]


async def test_thinking_of_an_earlier_turn_is_not_sent_with_the_next_one(tmp_path: Path) -> None:
    world = build_world(
        tmp_path,
        [answer([THINKING, TEXT]), text_answer("<reply>two</reply>", message_id="msg_2")],
    )
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 2, "@bot second"))
    sent = world.client.messages.requests[1]["messages"]
    assert "thinking" not in json.dumps(sent)
    assert sent[1] == {"role": "assistant", "content": [TEXT]}


async def test_thinking_inside_the_turn_stays_through_its_tool_rounds(tmp_path: Path) -> None:
    call = {"type": "tool_use", "id": "toolu_1", "name": "search_history", "input": {"query": "x"}}
    world = build_world(
        tmp_path,
        [
            answer([THINKING, call], message_id="msg_1", stop_reason="tool_use"),
            text_answer("<reply>done</reply>", message_id="msg_2"),
        ],
    )
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    inside = world.client.messages.requests[1]["messages"]
    assert [m["role"] for m in inside] == ["user", "assistant", "user"]
    assert inside[1]["content"] == [THINKING, call]


async def test_a_turn_after_a_tool_round_drops_the_thinking_of_both_rounds(
    tmp_path: Path,
) -> None:
    call = {"type": "tool_use", "id": "toolu_1", "name": "search_history", "input": {"query": "x"}}
    world = build_world(
        tmp_path,
        [
            answer([THINKING, call], message_id="msg_1", stop_reason="tool_use"),
            answer([REDACTED, TEXT], message_id="msg_2"),
            text_answer("<reply>again</reply>", message_id="msg_3"),
        ],
    )
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 2, "@bot second"))
    sent = world.client.messages.requests[2]["messages"]
    assert "thinking" not in json.dumps(sent)
    assert [m["role"] for m in sent] == ["user", "assistant", "user", "assistant", "user"]
    assert sent[1]["content"] == [call]


async def test_the_record_keeps_the_thinking(tmp_path: Path) -> None:
    world = build_world(tmp_path, [answer([THINKING, TEXT]), text_answer("<reply>b</reply>")])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 2, "@bot second"))
    assert THINKING in world.conversations.get(GROUP).messages[1]["content"]


async def test_the_summary_request_carries_no_thinking(tmp_path: Path) -> None:
    usage = {"input_tokens": 70_000, "output_tokens": 10}
    world = build_world(
        tmp_path,
        [answer([THINKING, TEXT], usage=usage), text_answer("Decided: Kyoto.", message_id="msg_s")],
    )
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    assert await world.rollover.roll_over_if_full(world.conversations.get(GROUP))
    assert "thinking" not in json.dumps(world.client.messages.requests[1]["messages"])
