"""One answer makes one poll: the poll-making tools run once, whatever the rounds and the
tools, and the other tools are not counted."""

from pathlib import Path

import pytest

from line_group_agent.agent.answerer import Answer
from line_group_agent.polls.poll_book import PollBook
from line_group_agent.polls.poll_tools import POLL_ALREADY_MADE_RESULT, poll_tools
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, NOW_FOR_TESTS, World, build_world

pytestmark = pytest.mark.anyio
MENTION = GroupMessage("2026-11-18T12:00:00+09:00", "99", "U1", "Aki", "@bot make a poll")
DATES = ["12/12", "12/19", "12/26"]
DATE_POLL = ("create_date_poll", {"title": "Dates", "dates": DATES})
CHOICE_POLL = ("create_poll", {"question": "Dates", "options": DATES})
OTHER_POLL = ("create_poll", {"question": "Where?", "options": ["Kyoto", "Osaka"]})


def calls(*calls_made: tuple[str, dict[str, object]], first_id: int = 1) -> dict[str, object]:
    content = [
        {"type": "tool_use", "id": f"toolu_{first_id + index}", "name": name, "input": data}
        for index, (name, data) in enumerate(calls_made)
    ]
    return answer(content, stop_reason="tool_use")


async def run_answers(tmp_path: Path, *rounds: dict[str, object]) -> tuple[World, PollBook, Answer]:
    book = PollBook(tmp_path / "state", lambda: NOW_FOR_TESTS)
    script = [*rounds, text_answer("<reply>done</reply>", message_id="msg_end")]
    world = build_world(tmp_path, script, tools=poll_tools(book))
    result = await world.answerer.answer(GROUP, MENTION)
    return world, book, result


def results_sent_after(world: World, request_index: int) -> list[dict[str, object]]:
    return world.client.messages.requests[request_index]["messages"][-1]["content"]


@pytest.mark.parametrize(
    ("first", "second"),
    [(DATE_POLL, CHOICE_POLL), (CHOICE_POLL, DATE_POLL), (CHOICE_POLL, OTHER_POLL)],
)
async def test_a_second_poll_in_the_same_round_is_not_made(
    tmp_path: Path, first: tuple[str, dict[str, object]], second: tuple[str, dict[str, object]]
) -> None:
    world, book, result = await run_answers(tmp_path, calls(first, second))
    assert len(result.extras) == 1
    assert book.get(GROUP, "p1") is not None and book.get(GROUP, "p2") is None
    made, refused = results_sent_after(world, 1)
    assert "is_error" not in made and "p1" in str(made["content"])
    assert refused["content"] == POLL_ALREADY_MADE_RESULT.format(poll_id="p1")
    assert "is_error" not in refused


async def test_a_second_poll_in_a_later_round_is_not_made(tmp_path: Path) -> None:
    world, book, result = await run_answers(
        tmp_path, calls(DATE_POLL), calls(OTHER_POLL, first_id=2)
    )
    assert len(result.extras) == 1
    assert book.get(GROUP, "p2") is None
    [refused] = results_sent_after(world, 2)
    assert refused["content"] == POLL_ALREADY_MADE_RESULT.format(poll_id="p1")


async def test_the_next_answer_can_make_a_poll_again(tmp_path: Path) -> None:
    book = PollBook(tmp_path / "state", lambda: NOW_FOR_TESTS)
    script = [
        calls(DATE_POLL),
        text_answer("<reply>first</reply>", message_id="msg_2"),
        calls(OTHER_POLL, first_id=2),
        text_answer("<reply>second</reply>", message_id="msg_4"),
    ]
    world = build_world(tmp_path, script, tools=poll_tools(book))
    await world.answerer.answer(GROUP, MENTION)
    result = await world.answerer.answer(GROUP, MENTION)
    assert len(result.extras) == 1
    assert book.get(GROUP, "p2") is not None


async def test_a_poll_that_could_not_be_made_does_not_use_up_the_answer(tmp_path: Path) -> None:
    broken = ("create_poll", {"question": "Where?", "options": ["Kyoto"]})
    world, book, result = await run_answers(tmp_path, calls(broken, DATE_POLL))
    assert len(result.extras) == 1
    failed, made = results_sent_after(world, 1)
    assert failed["is_error"] is True
    assert "p1" in str(made["content"]) and book.get(GROUP, "p1") is not None


async def test_the_tools_that_make_no_poll_still_run_after_a_poll(tmp_path: Path) -> None:
    world, book, _ = await run_answers(
        tmp_path,
        calls(DATE_POLL),
        calls(("poll_results", {}), ("close_poll", {}), first_id=2),
    )
    results, closed = results_sent_after(world, 2)
    assert "is_error" not in results and "is_error" not in closed
    poll = book.get(GROUP, "p1")
    assert poll is not None and poll.is_closed
