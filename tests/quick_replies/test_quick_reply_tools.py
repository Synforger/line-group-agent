import pytest

from line_group_agent.agent.client_tool import ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.line_api.quick_reply import QuickReplyItem
from line_group_agent.quick_replies.quick_reply_tools import quick_reply_tools
from line_group_agent.records.group_log import GroupMessage

MENTION = GroupMessage("t", "1", "U1", "Aki", "@bot shall we?")


def run(
    tool_input: object, *, call_name: str | None = "Sora", output: TurnOutput | None = None
) -> tuple[ToolOutcome, TurnOutput]:
    [tool] = quick_reply_tools(call_name)
    output = output or TurnOutput()
    return tool.run(tool_input, ToolTurn("Cgroup", MENTION, output)), output


def test_each_option_becomes_a_button_that_sends_the_call_name_and_the_option() -> None:
    outcome, output = run({"options": ["Kyoto", "Osaka"]})
    assert not outcome.is_error
    assert output.quick_replies == [
        QuickReplyItem("Kyoto", "Sora、Kyoto"),
        QuickReplyItem("Osaka", "Sora、Osaka"),
    ]


def test_without_a_call_name_a_tap_sends_the_option_alone() -> None:
    _, output = run({"options": ["Yes"]}, call_name=None)
    assert output.quick_replies == [QuickReplyItem("Yes", "Yes")]


def test_a_long_option_is_cut_on_the_button_but_not_in_the_text() -> None:
    long = "x" * 40
    _, output = run({"options": [long]})
    [item] = output.quick_replies
    assert item.label == "x" * 19 + "…" and item.text == f"Sora、{long}"


def test_the_text_a_tap_sends_stays_within_LINEs_limit() -> None:
    _, output = run({"options": ["y" * 500]})
    assert len(output.quick_replies[0].text) == 300


def test_options_are_made_one_line_and_repeats_are_dropped() -> None:
    _, output = run({"options": [" Yes\n please ", "Yes please", "No"]})
    assert [i.label for i in output.quick_replies] == ["Yes please", "No"]


def test_a_second_call_replaces_the_first() -> None:
    output = TurnOutput()
    run({"options": ["A", "B"]}, output=output)
    run({"options": ["C"]}, output=output)
    assert [i.label for i in output.quick_replies] == ["C"]


@pytest.mark.parametrize(
    "tool_input",
    [None, {}, {"options": []}, {"options": [""]}, {"options": "Yes"}, {"options": [1]},
     {"options": [str(n) for n in range(6)]}],
)  # fmt: skip
def test_a_call_that_is_not_one_to_five_options_adds_no_buttons(tool_input: object) -> None:
    outcome, output = run(tool_input)
    assert outcome.is_error and output.quick_replies == []


@pytest.mark.anyio
async def test_the_model_can_put_buttons_under_its_reply(tmp_path: object) -> None:
    from pathlib import Path

    from tests.fakes import answer, text_answer
    from tests.world import GROUP, build_world

    call = {
        "type": "tool_use",
        "id": "toolu_1",
        "name": "suggest_replies",
        "input": {"options": ["Kyoto", "Osaka"]},
    }
    world = build_world(
        Path(str(tmp_path)),
        [
            answer([call], stop_reason="tool_use"),
            text_answer("<reply>Where?</reply>", message_id="m2"),
        ],
        tools=quick_reply_tools("Sora"),
    )
    result = await world.answerer.answer(GROUP, MENTION)
    assert result.text == "Where?"
    assert [i.text for i in result.quick_replies] == ["Sora、Kyoto", "Sora、Osaka"]
