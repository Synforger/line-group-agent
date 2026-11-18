"""The running conversation: one record per group, rebuilt after a restart, each turn
adding only what was said since the last one, and a full conversation rolled over into
a summary that opens the next generation."""

import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.prompt import SUMMARY_REQUEST
from line_group_agent.records.conversation_log import SUMMARY_PREFIX
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


def said(world: World, number: int, text: str, *, from_bot: bool = False) -> GroupMessage:
    message = GroupMessage(
        f"2026-11-18T12:{number:02d}:00+09:00", f"m{number}", "U1", "Aki", text, from_bot
    )
    world.group_log.add(GROUP, message)
    return message


def usage(tokens: int) -> dict[str, Any]:
    return {"input_tokens": 100, "cache_read_input_tokens": tokens - 100, "output_tokens": 10}


def reply(text: str, number: int, tokens: int = 1000) -> dict[str, Any]:
    return text_answer(f"<reply>{text}</reply>", message_id=f"msg_{number}", usage=usage(tokens))


def rows(world: World) -> list[dict[str, Any]]:
    path = world.conversations.get(GROUP).log.path
    return [json.loads(line) for line in path.read_text().splitlines()]


async def test_the_record_of_a_group_is_named_from_its_id(tmp_path: Path) -> None:
    world = build_world(tmp_path, [reply("a", 1)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot hi"))
    assert (tmp_path / "state" / "conversations" / "g-callowed.jsonl").exists()


async def test_the_second_turn_continues_the_first_and_adds_only_what_was_said_since(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [reply("one", 1), reply("two", 2)])
    said(world, 0, "before the first mention")
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    world.group_log.add(GROUP, said_bot := GroupMessage("t", "bot-1", None, None, "one", True))
    assert said_bot.from_bot
    said(world, 2, "chat one")
    said(world, 3, "chat two")
    await world.answerer.answer(GROUP, said(world, 4, "@bot second"))

    second = world.client.messages.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[0]["content"].count("before the first mention") == 1
    assert second[1]["content"] == [{"type": "text", "text": "<reply>one</reply>"}]
    turn = second[2]["content"]
    assert "chat one" in turn and "chat two" in turn and "@bot second" in turn
    assert "before the first mention" not in turn and "@bot first" not in turn
    assert "your_reply" not in turn
    assert not turn.startswith(SUMMARY_PREFIX)


async def test_a_turn_after_a_mention_with_no_reply_does_not_repeat_that_mention(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer("no mark", usage=usage(900)), reply("x", 2)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    said(world, 2, "later chat")
    await world.answerer.answer(GROUP, said(world, 3, "@bot second"))
    turn = world.client.messages.requests[1]["messages"][2]["content"]
    assert "later chat" in turn and "@bot first" not in turn


async def test_the_conversation_is_rebuilt_from_the_record_after_a_restart(tmp_path: Path) -> None:
    world = build_world(tmp_path, [reply("one", 1)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    restarted = build_world(tmp_path, [reply("two", 2)])
    said(restarted, 2, "while it was down")
    await restarted.answerer.answer(GROUP, said(restarted, 3, "@bot second"))
    messages = restarted.client.messages.requests[0]["messages"]
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert "@bot first" in messages[0]["content"]
    assert "while it was down" in messages[2]["content"]
    assert restarted.conversations.get(GROUP).context_tokens == 1000


async def test_the_assistant_turns_go_back_exactly_as_they_were_recorded(tmp_path: Path) -> None:
    blocks = [
        {"type": "thinking", "thinking": "hm", "signature": "sig=="},
        {"type": "text", "text": "<reply>ok</reply>"},
    ]
    world = build_world(tmp_path, [answer(blocks, usage=usage(500)), reply("two", 2)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 2, "@bot second"))
    sent = world.client.messages.requests[1]["messages"][1]
    assert sent == {"role": "assistant", "content": blocks}
    assert [r["message"]["content"] for r in rows(world) if r["type"] == "assistant"][0] == blocks


async def test_a_tool_call_left_without_a_result_does_not_break_the_next_turn(
    tmp_path: Path,
) -> None:
    call = {"type": "tool_use", "id": "toolu_1", "name": "search_history", "input": {"query": "x"}}
    stuck = answer([call], stop_reason="tool_use", usage=usage(500))
    world = build_world(tmp_path, [stuck, reply("fine", 2)], max_tool_rounds=0)
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 2, "@bot second"))
    last = world.client.messages.requests[1]["messages"][2]["content"]
    assert last[0]["type"] == "tool_result" and last[0]["tool_use_id"] == "toolu_1"
    assert last[0]["is_error"] is True and last[1]["type"] == "text"


async def test_a_conversation_over_the_rollover_percent_is_summarized_after_its_answer(
    tmp_path: Path,
) -> None:
    summary = text_answer("Decided: Kyoto.", message_id="msg_s", usage=usage(70_000))
    world = build_world(tmp_path, [reply("one", 1, 70_000), summary])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    assert len(world.client.messages.requests) == 1

    assert await world.rollover.roll_over_if_full(world.conversations.get(GROUP))
    request = world.client.messages.requests[1]
    assert request["tool_choice"] == {"type": "none"}
    assert request["max_tokens"] == 2048
    assert request["messages"][-1] == {"role": "user", "content": SUMMARY_REQUEST}
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user"]
    assert len(rows(world)) == 2
    journal = tmp_path / "state" / "groups" / GROUP / "journal" / "2026-11-18-gen1.md"
    assert journal.read_text() == "Decided: Kyoto.\n"


async def test_a_conversation_under_the_percent_is_left_alone(tmp_path: Path) -> None:
    world = build_world(tmp_path, [reply("one", 1, 59_000)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    assert not await world.rollover.roll_over_if_full(world.conversations.get(GROUP))
    assert len(world.client.messages.requests) == 1


async def test_the_summary_opens_the_next_generation_with_the_recent_messages(
    tmp_path: Path,
) -> None:
    summary = text_answer("Decided: Kyoto.", message_id="msg_s", usage=usage(70_000))
    world = build_world(tmp_path, [reply("one", 1, 70_000), summary, reply("two", 3, 3_000)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    world.group_log.add(GROUP, GroupMessage("t", "bot-1", None, None, "one", True))
    await world.rollover.roll_over_if_full(world.conversations.get(GROUP))
    said(world, 2, "after the summary")
    await world.answerer.answer(GROUP, said(world, 3, "@bot second"))

    messages = world.client.messages.requests[2]["messages"]
    assert len(messages) == 1
    content = messages[0]["content"]
    assert content.startswith(f"{SUMMARY_PREFIX}\nDecided: Kyoto.\n\nGroup messages")
    assert "after the summary" in content and "@bot second" in content
    assert "<your_reply" in content
    conversation = world.conversations.get(GROUP)
    assert conversation.generation == 2 and conversation.pending_summary is None
    assert conversation.context_tokens == 3_000
    assert [r["message"]["content"] for r in rows(world) if r["type"] == "user"][1].startswith(
        SUMMARY_PREFIX
    )


async def test_a_restart_after_the_summary_still_opens_the_next_generation_with_it(
    tmp_path: Path,
) -> None:
    summary = text_answer("Decided: Kyoto.", message_id="msg_s", usage=usage(70_000))
    world = build_world(tmp_path, [reply("one", 1, 70_000), summary])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    await world.rollover.roll_over_if_full(world.conversations.get(GROUP))

    restarted = build_world(tmp_path, [reply("two", 3)])
    await restarted.answerer.answer(GROUP, said(restarted, 3, "@bot second"))
    sent = restarted.client.messages.requests[0]["messages"]
    assert len(sent) == 1 and sent[0]["content"].startswith(SUMMARY_PREFIX)
    again = build_world(tmp_path, [])
    assert again.conversations.get(GROUP).generation == 2


async def test_a_summary_is_made_only_once_while_it_waits(tmp_path: Path) -> None:
    summary = text_answer("S", message_id="msg_s", usage=usage(70_000))
    world = build_world(tmp_path, [reply("one", 1, 70_000), summary])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    conversation = world.conversations.get(GROUP)
    assert await world.rollover.roll_over_if_full(conversation)
    assert not await world.rollover.roll_over_if_full(conversation)
    assert len(world.client.messages.requests) == 2


async def test_the_summary_cost_counts_against_the_group_and_the_whole(tmp_path: Path) -> None:
    summary = text_answer(
        "S", message_id="msg_s", usage={"input_tokens": 1_000_000, "output_tokens": 1}
    )
    world = build_world(tmp_path, [reply("one", 1, 70_000), summary])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    before = world.books.group_figure(GROUP)["spent"]
    await world.rollover.roll_over_if_full(world.conversations.get(GROUP))
    assert world.books.group_figure(GROUP)["spent"] > before + 10


async def test_an_empty_or_failed_summary_leaves_the_conversation_as_it_was(
    tmp_path: Path,
) -> None:
    empty = answer([{"type": "text", "text": "  "}], message_id="msg_s")
    world = build_world(tmp_path, [reply("one", 1, 70_000), empty])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    conversation = world.conversations.get(GROUP)
    assert not await world.rollover.roll_over_if_full(conversation)
    assert not await world.rollover.roll_over_if_full(conversation)
    assert conversation.pending_summary is None and conversation.generation == 1


async def test_no_summary_is_asked_for_when_the_group_cannot_pay_for_it(tmp_path: Path) -> None:
    world = build_world(tmp_path, [reply("one", 1, 70_000)])
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    world.books.add(GROUP, 999.99)
    assert not await world.rollover.roll_over_if_full(world.conversations.get(GROUP))
    assert len(world.client.messages.requests) == 1


async def test_a_quiet_group_is_rolled_over_at_the_idle_percent(tmp_path: Path) -> None:
    summary = text_answer("S", message_id="msg_s", usage=usage(45_000))
    world = build_world(tmp_path, [reply("one", 1, 45_000), summary])
    await world.watcher.note_message(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    conversation = world.conversations.get(GROUP)
    assert not await world.rollover.roll_over_if_full(conversation)

    world.clock.advance(hours=5)
    await world.watcher.patrol()
    assert len(world.client.messages.requests) == 1
    world.clock.advance(hours=1.1)
    await world.watcher.patrol()
    assert len(world.client.messages.requests) == 2
    assert conversation.pending_summary == "S"


async def test_the_idle_rollover_follows_the_settings_file(tmp_path: Path) -> None:
    summary = text_answer("S", message_id="msg_s", usage=usage(45_000))
    world = build_world(tmp_path, [reply("one", 1, 45_000), summary])
    await world.watcher.note_message(GROUP, said(world, 1, "@bot first"))
    await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    world.write_settings(idle_hours=24, idle_rollover_percent=40)
    world.clock.advance(hours=7)
    await world.watcher.patrol()
    assert len(world.client.messages.requests) == 1
    world.write_settings(idle_hours=1, idle_rollover_percent=50)
    await world.watcher.patrol()
    assert len(world.client.messages.requests) == 1
    world.write_settings(idle_hours=1, idle_rollover_percent=40)
    await world.watcher.patrol()
    assert len(world.client.messages.requests) == 2


async def test_the_group_limit_stops_the_call_before_the_whole_limit_does(tmp_path: Path) -> None:
    world = build_world(tmp_path, [reply("one", 1)], allowed_group_ids=["Callowed", "Cother"])
    assert world.conversations.count() == 2
    world.books.add(GROUP, 499)
    answered = await world.answerer.answer(GROUP, said(world, 1, "@bot first"))
    assert answered.text == "This month's budget is used up."
    assert world.client.messages.requests == []
    assert world.books.can_afford("Cother", 100)


async def test_a_five_minute_cache_is_sent_when_the_config_says_so(tmp_path: Path) -> None:
    world = build_world(tmp_path, [reply("a", 1)], cache_ttl="5m")
    await world.answerer.answer(GROUP, said(world, 1, "@bot hi"))
    request = world.client.messages.requests[0]
    assert request["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
    assert request["system"][0]["cache_control"] == {"type": "ephemeral", "ttl": "5m"}
