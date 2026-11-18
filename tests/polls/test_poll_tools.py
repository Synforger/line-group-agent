import json
from pathlib import Path

import pytest

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.polls.poll_book import PollBook
from line_group_agent.polls.poll_tools import clean_labels, poll_tools
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, NOW_FOR_TESTS, build_world

MENTION = GroupMessage("t", "99", "U1", "Aki", "@bot vote")


def tools_for(tmp_path: Path) -> tuple[dict[str, ClientTool], PollBook]:
    book = PollBook(tmp_path, lambda: NOW_FOR_TESTS)
    return {tool.name: tool for tool in poll_tools(book)}, book


def run(
    tool: ClientTool, tool_input: object, output: TurnOutput | None = None
) -> tuple[ToolOutcome, TurnOutput]:
    output = output or TurnOutput()
    return tool.run(tool_input, ToolTurn(GROUP, MENTION, output)), output


def test_create_poll_keeps_the_poll_and_adds_its_card_and_record_line(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    outcome, output = run(
        tools["create_poll"], {"question": "Where?", "options": ["Kyoto", "Osaka"]}
    )
    assert not outcome.is_error and "p1" in outcome.content
    [extra] = output.extras
    assert extra.message["type"] == "flex"
    assert extra.record_line == "[投票] p1 Where? 1. Kyoto / 2. Osaka"
    poll = book.get(GROUP, "p1")
    assert poll is not None and not poll.multiple


def test_create_poll_can_allow_several_picks(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    run(tools["create_poll"], {"question": "Q", "options": ["A", "B"], "multiple": True})
    poll = book.get(GROUP)
    assert poll is not None and poll.multiple


@pytest.mark.parametrize(
    "tool_input",
    [
        None,
        {"question": "", "options": ["A", "B"]},
        {"question": "Q", "options": ["A"]},
        {"question": "Q", "options": ["A", "A"]},
        {"question": "Q", "options": ["A", ""]},
        {"question": "Q", "options": "AB"},
        {"question": "Q", "options": [str(n) for n in range(11)]},
        {"question": "Q", "options": ["A", 3]},
    ],
)
def test_create_poll_refuses_a_call_that_is_not_two_to_ten_options(
    tmp_path: Path, tool_input: object
) -> None:
    tools, book = tools_for(tmp_path)
    outcome, output = run(tools["create_poll"], tool_input)
    assert outcome.is_error and output.extras == [] and book.get(GROUP) is None


def test_create_poll_makes_nothing_when_the_reply_has_no_room_left(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    output = TurnOutput()
    for _ in range(MAX_EXTRA_MESSAGES):
        run(tools["create_poll"], {"question": "Q", "options": ["A", "B"]}, output)
    outcome, _ = run(tools["create_poll"], {"question": "Q", "options": ["A", "B"]}, output)
    assert outcome.is_error and len(output.extras) == MAX_EXTRA_MESSAGES
    assert book.get(GROUP, "p4") is None


def test_poll_results_reads_the_newest_open_poll_or_the_one_asked_for(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    run(tools["create_poll"], {"question": "One", "options": ["A", "B"]})
    run(tools["create_poll"], {"question": "Two", "options": ["C", "D"]})
    book.vote(GROUP, "p1", 1, "U1", "Aki")
    assert "Two" in run(tools["poll_results"], {})[0].content
    first = run(tools["poll_results"], {"poll_id": "p1"})[0].content
    assert "B: 1 (Aki)" in first


def test_poll_results_without_any_poll_is_an_error(tmp_path: Path) -> None:
    tools, _ = tools_for(tmp_path)
    assert run(tools["poll_results"], {})[0].is_error
    assert run(tools["poll_results"], {"poll_id": "p7"})[0].is_error


def test_close_poll_closes_and_reports_the_final_count(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    run(tools["create_poll"], {"question": "One", "options": ["A", "B"]})
    outcome, _ = run(tools["close_poll"], {})
    assert not outcome.is_error and "closed" in outcome.content
    poll = book.get(GROUP, "p1")
    assert poll is not None and poll.is_closed
    assert run(tools["close_poll"], {})[0].is_error


def test_labels_are_cut_to_a_button_and_must_be_different() -> None:
    assert clean_labels(["a" * 30, " b  c "]) == ["a" * 19 + "…", "b c"]
    assert clean_labels(["a", "a"]) is None


@pytest.mark.anyio
async def test_the_model_can_make_a_poll_through_the_whole_answer(tmp_path: Path) -> None:
    book = PollBook(tmp_path / "state", lambda: NOW_FOR_TESTS)
    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "create_poll",
        "input": {"question": "Where?", "options": ["Kyoto", "Osaka"]},
    }
    world = build_world(
        tmp_path,
        [
            answer([call], stop_reason="tool_use"),
            text_answer("<reply>Vote!</reply>", message_id="m2"),
        ],
        tools=poll_tools(book),
    )
    result = await world.answerer.answer(GROUP, MENTION)
    assert result.text == "Vote!" and len(result.extras) == 1
    names = [tool["name"] for tool in world.client.messages.requests[0]["tools"]]
    assert {"create_poll", "poll_results", "close_poll"} <= set(names)
    [tool_result] = world.client.messages.requests[1]["messages"][-1]["content"]
    assert "p1" in tool_result["content"]
    assert json.loads((tmp_path / "state/groups" / GROUP / "polls.json").read_text())["polls"]
