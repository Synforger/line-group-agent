"""A message that is deleted is taken out of the summaries that quoted it."""

import os
from datetime import date
from pathlib import Path

import pytest

from line_group_agent.agent.prompt import DELETED_MARK, SCRUB_REQUEST
from line_group_agent.agent.summary_scrubber import MIN_SCRUBBED_CHARS
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio
SECRET = "my passport number is X123456"
SUMMARY = f"The group plans Kyoto. Aki said: {SECRET}. Sora likes temples."
CLEAN = "The group plans Kyoto. Sora likes temples."


def deleted(text: str, *, image_file: str | None = None) -> GroupMessage:
    return GroupMessage("t", "m1", "U1", "Aki", text, image_file=image_file)


def write_summary(world: World, generation: int = 1, text: str = SUMMARY) -> Path:
    return world.journal.write(GROUP, generation, text, date(2026, 11, 1))


def request_text(world: World, index: int = 0) -> str:
    return str(world.client.messages.requests[index]["messages"][-1]["content"])


async def test_a_summary_that_quotes_a_deleted_message_is_rewritten_by_the_model(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    path = write_summary(world)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    assert await world.scrubber.scrub_pending(GROUP) == 1
    assert path.read_text() == CLEAN + "\n"
    [request] = world.client.messages.requests
    assert request["messages"][-1]["content"].startswith(SCRUB_REQUEST)
    assert SUMMARY in request_text(world) and f"<deleted>{SECRET}</deleted>" in request_text(world)
    assert request["tool_choice"] == {"type": "none"}


async def test_the_cost_of_the_rewrite_counts_for_the_group(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    write_summary(world)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert world.books.overall.spent > 0


async def test_the_modification_time_of_the_summary_is_kept(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    path = write_summary(world)
    os.utime(path, (1_700_000_000, 1_700_000_000))
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert path.stat().st_mtime == 1_700_000_000


async def test_a_rewrite_that_still_holds_the_deleted_text_is_cleaned_in_code(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer(f"Notes. {SECRET}. Done.")])
    path = write_summary(world)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert path.read_text() == f"Notes. {DELETED_MARK}. Done.\n"


async def test_when_the_model_cannot_be_asked_the_text_is_replaced_in_code(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [])
    path = write_summary(world)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert path.read_text() == SUMMARY.replace(SECRET, DELETED_MARK) + "\n"


async def test_when_the_budget_is_gone_the_model_is_not_called_and_the_text_is_replaced(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    path = write_summary(world)
    world.books.overall.add(10_000)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert world.client.messages.requests == []
    assert DELETED_MARK in path.read_text() and SECRET not in path.read_text()


async def test_a_summary_that_does_not_quote_it_is_not_touched_and_costs_nothing(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    path = write_summary(world, text=CLEAN)
    before = path.stat().st_mtime_ns
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    assert await world.scrubber.scrub_pending(GROUP) == 0
    assert world.client.messages.requests == [] and path.stat().st_mtime_ns == before


async def test_every_generation_that_quotes_it_is_rewritten(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN), text_answer("Second, clean.")])
    first = write_summary(world, 1)
    second = write_summary(world, 2, text=f"Again: {SECRET}.")
    other = write_summary(world, 3, text="Nothing to see.")
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    assert await world.scrubber.scrub_pending(GROUP) == 2
    assert first.read_text() == CLEAN + "\n" and second.read_text() == "Second, clean.\n"
    assert other.read_text() == "Nothing to see.\n"


async def test_a_text_is_looked_for_once_and_forgotten(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    write_summary(world)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert await world.scrubber.scrub_pending(GROUP) == 0


async def test_a_short_text_and_a_photo_are_not_searched_for(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    write_summary(world, text="Plans: ok, w and [写真] were said.")
    short = "x" * (MIN_SCRUBBED_CHARS - 1)
    world.scrubber.note_deleted(
        GROUP, [deleted("ok"), deleted(short), deleted("[写真]", image_file="1.jpg")]
    )
    assert await world.scrubber.scrub_pending(GROUP) == 0
    assert world.client.messages.requests == []


async def test_the_waiting_summary_and_the_row_that_opened_the_conversation_follow_the_file(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>"), text_answer(CLEAN)])
    write_summary(world)
    conversation = world.conversations.get(GROUP)
    conversation.set_pending_summary(SUMMARY, world.clock())
    mention = GroupMessage("t99", "99", "U1", "Aki", "@bot hi")
    world.group_log.add(GROUP, mention)
    await world.answerer.answer(GROUP, mention)
    assert conversation.has_opened_with(SUMMARY)
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert conversation.has_opened_with(CLEAN) and not conversation.has_opened_with(SUMMARY)
    record = conversation.log.path.read_text()
    assert SECRET not in record and CLEAN in record


async def test_a_summary_still_waiting_to_open_the_next_conversation_is_rewritten(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer(CLEAN)])
    write_summary(world)
    conversation = world.conversations.get(GROUP)
    conversation.set_pending_summary(SUMMARY, world.clock())
    world.scrubber.note_deleted(GROUP, [deleted(SECRET)])
    await world.scrubber.scrub_pending(GROUP)
    assert conversation.pending_summary == CLEAN


async def test_deleting_a_message_and_finishing_the_answer_scrubs_the_summaries(
    tmp_path: Path,
) -> None:
    summary_turn = text_answer("A fresh summary.", message_id="msg_s")
    world = build_world(
        tmp_path, [text_answer("<reply>ok</reply>"), text_answer(CLEAN), summary_turn]
    )
    path = write_summary(world)
    secret_message = GroupMessage("t1", "m1", "U1", "Aki", SECRET)
    world.group_log.add(GROUP, secret_message)
    mention = GroupMessage("t2", "99", "U1", "Aki", "@bot hi")
    world.group_log.add(GROUP, mention)
    await world.answerer.answer(GROUP, mention)
    assert world.deleter.delete(GROUP, {"m1"}) == 1
    assert path.read_text() == SUMMARY + "\n"
    await world.watcher.after_deletion(GROUP)
    assert path.read_text() == CLEAN + "\n"
    first_request = request_text(world, 1)
    assert SECRET in first_request and "Summary:" in first_request
