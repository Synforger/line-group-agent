import json
from pathlib import Path

import pytest

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.polls.poll_book import PollBook
from line_group_agent.polls.poll_tools import clean_labels, made_poll_id, poll_tools
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


def test_a_poll_made_and_closed_in_the_same_reply_sends_no_card(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    output = TurnOutput()
    run(tools["create_poll"], {"question": "test", "options": ["a", "b"]}, output)
    run(tools["create_poll"], {"question": "Where?", "options": ["Kyoto", "Osaka"]}, output)
    outcome, _ = run(tools["close_poll"], {"poll_id": "p1"}, output)
    assert not outcome.is_error and "not sent" in outcome.content
    [extra] = output.extras
    assert extra.record_line.startswith("[投票] p2 Where?")
    poll = book.get(GROUP, "p1")
    assert poll is not None and poll.is_closed


def test_closing_a_poll_of_an_earlier_reply_leaves_this_replys_cards(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    run(tools["create_poll"], {"question": "Old", "options": ["a", "b"]})
    output = TurnOutput()
    run(tools["create_poll"], {"question": "New", "options": ["c", "d"]}, output)
    outcome, _ = run(tools["close_poll"], {"poll_id": "p1"}, output)
    assert not outcome.is_error and "not sent" not in outcome.content
    [extra] = output.extras
    assert extra.record_line.startswith("[投票] p2 New")


def test_a_date_poll_made_and_closed_in_the_same_reply_sends_no_card(tmp_path: Path) -> None:
    tools, _ = tools_for(tmp_path)
    output = TurnOutput()
    run(tools["create_date_poll"], {"title": "Day", "dates": ["11/23", "11/24"]}, output)
    run(tools["close_poll"], {}, output)
    assert output.extras == []


@pytest.mark.parametrize("name", ["create_poll", "create_date_poll"])
def test_the_tools_that_make_a_poll_say_not_to_make_one_to_test_the_tools(
    tmp_path: Path, name: str
) -> None:
    tools, _ = tools_for(tmp_path)
    assert "Do not make a poll to test the tools." in tools[name].definition["description"]


def test_create_date_poll_makes_a_multiple_date_poll_with_its_card(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    outcome, output = run(
        tools["create_date_poll"], {"title": "Trip day", "dates": ["11/23(Sat)", "11/24(Sun)"]}
    )
    assert not outcome.is_error
    poll = book.get(GROUP, "p1")
    assert poll is not None and poll.kind == "date" and poll.multiple
    assert output.extras[0].record_line == "[日程] p1 Trip day 1. 11/23(Sat) / 2. 11/24(Sun)"
    buttons = output.extras[0].message["contents"]["body"]["contents"][2:]
    assert [b["action"]["data"] for b in buttons] == ["poll:p1:0", "poll:p1:1"]


@pytest.mark.parametrize(
    "tool_input",
    [None, {"title": "", "dates": ["a", "b"]}, {"title": "T", "dates": ["a"]}, {"title": "T"}],
)
def test_create_date_poll_refuses_a_call_without_a_title_and_two_dates(
    tmp_path: Path, tool_input: object
) -> None:
    tools, book = tools_for(tmp_path)
    outcome, output = run(tools["create_date_poll"], tool_input)
    assert outcome.is_error and "dates" in outcome.content
    assert output.extras == [] and book.get(GROUP) is None


def test_the_date_count_shows_who_is_free_each_day(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    run(tools["create_date_poll"], {"title": "Trip day", "dates": ["Sat", "Sun"]})
    book.vote(GROUP, "p1", 0, "U1", "Aki")
    book.vote(GROUP, "p1", 1, "U1", "Aki")
    book.vote(GROUP, "p1", 1, "U2", "Sora")
    text = run(tools["poll_results"], {})[0].content
    assert "1. Sat: 1 (Aki)" in text and "2. Sun: 2 (Aki, Sora)" in text


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
    assert {"create_poll", "poll_results", "close_poll", "withdraw_vote"} <= set(names)
    [tool_result] = world.client.messages.requests[1]["messages"][-1]["content"]
    assert "p1" in tool_result["content"]
    assert json.loads((tmp_path / "state/groups" / GROUP / "polls.json").read_text())["polls"]


def _withdraw(tmp_path: Path, tool_input: object, user_id: str | None = "U1"):
    tools, book = tools_for(tmp_path)
    run(tools["create_poll"], {"question": "Q", "options": ["A", "B"]})
    book.vote(GROUP, "p1", 0, "U1", "Aki")
    book.vote(GROUP, "p1", 1, "U2", "Sora")
    mention = GroupMessage("t", "99", user_id, "x", "@bot cancel my vote")
    outcome = tools["withdraw_vote"].run(tool_input, ToolTurn(GROUP, mention, TurnOutput()))
    poll = book.get(GROUP, "p1")
    assert poll is not None
    return outcome, [[v.user_id for v in o.voters] for o in poll.options]


def test_withdraw_vote_takes_back_only_the_vote_of_the_member_who_asked(tmp_path: Path) -> None:
    outcome, voters = _withdraw(tmp_path, {})
    assert not outcome.is_error and "p1" in outcome.content
    assert voters == [[], ["U2"]]


def test_withdraw_vote_can_name_the_poll(tmp_path: Path) -> None:
    outcome, voters = _withdraw(tmp_path, {"poll_id": "p1"})
    assert not outcome.is_error and voters == [[], ["U2"]]


def test_withdraw_vote_for_a_member_without_a_vote_changes_nothing(tmp_path: Path) -> None:
    outcome, voters = _withdraw(tmp_path, {}, user_id="U3")
    assert outcome.is_error and voters == [["U1"], ["U2"]]


def test_withdraw_vote_needs_to_know_who_asked(tmp_path: Path) -> None:
    outcome, voters = _withdraw(tmp_path, {}, user_id=None)
    assert outcome.is_error and voters == [["U1"], ["U2"]]


def test_withdraw_vote_refuses_an_unknown_or_closed_poll(tmp_path: Path) -> None:
    tools, book = tools_for(tmp_path)
    assert run(tools["withdraw_vote"], {})[0].is_error
    run(tools["create_poll"], {"question": "Q", "options": ["A", "B"]})
    book.vote(GROUP, "p1", 0, "U1", "Aki")
    assert run(tools["withdraw_vote"], {"poll_id": "p9"})[0].is_error
    book.close(GROUP, "p1")
    outcome, _ = run(tools["withdraw_vote"], {"poll_id": "p1"})
    assert outcome.is_error and "closed" in outcome.content
    poll = book.get(GROUP, "p1")
    assert poll is not None and len(poll.options[0].voters) == 1


def test_with_a_liff_app_the_card_opens_the_voting_page_of_the_poll_just_made(
    tmp_path: Path,
) -> None:
    book = PollBook(tmp_path, lambda: NOW_FOR_TESTS)
    tools = {tool.name: tool for tool in poll_tools(book, liff_id="1234567890-AbCdEfGh")}
    _, output = run(tools["create_poll"], {"question": "Where?", "options": ["Kyoto", "Osaka"]})
    poll = book.get(GROUP, "p1")
    assert poll is not None
    [button] = [
        entry
        for entry in output.extras[0].message["contents"]["body"]["contents"]
        if entry["type"] == "button"
    ]
    assert button["action"]["uri"] == f"https://liff.line.me/1234567890-AbCdEfGh?p={poll.link_id}"
    assert output.extras[0].record_line == "[投票] p1 Where? 1. Kyoto / 2. Osaka"


def test_with_a_liff_app_a_date_poll_card_opens_the_page_too(tmp_path: Path) -> None:
    book = PollBook(tmp_path, lambda: NOW_FOR_TESTS)
    tools = {tool.name: tool for tool in poll_tools(book, liff_id="1234567890-AbCdEfGh")}
    _, output = run(tools["create_date_poll"], {"title": "Day", "dates": ["Sat", "Sun"]})
    buttons = [
        entry["action"]["type"]
        for entry in output.extras[0].message["contents"]["body"]["contents"]
        if entry["type"] == "button"
    ]
    assert buttons == ["uri"]


def test_the_made_poll_id_is_read_back_from_the_result_of_a_made_poll(tmp_path: Path) -> None:
    tools, _ = tools_for(tmp_path)
    made, _ = run(tools["create_poll"], {"question": "Q", "options": ["A", "B"]})
    refused, _ = run(tools["create_poll"], {"question": "Q", "options": ["A"]})
    assert made_poll_id(made) == "p1"
    assert made_poll_id(refused) is None
    assert made_poll_id(ToolOutcome("Poll p9 is sent as a card", is_error=True)) is None


def test_each_creating_tool_tells_the_model_not_to_make_both_for_the_same_dates() -> None:
    book = PollBook(Path("unused"), lambda: NOW_FOR_TESTS)
    definitions = {tool.name: tool.definition["description"] for tool in poll_tools(book)}
    assert "create_date_poll" in definitions["create_poll"]
    assert "create_poll" in definitions["create_date_poll"]
