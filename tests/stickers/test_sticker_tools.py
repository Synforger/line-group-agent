import pytest

from line_group_agent.agent.client_tool import ClientTool, ToolTurn
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.records.group_log import GroupMessage
from line_group_agent.stickers.default_stickers import DEFAULT_STICKERS
from line_group_agent.stickers.sticker import Sticker
from line_group_agent.stickers.sticker_tools import sticker_tools

MENTION = GroupMessage("t", "99", "U1", "Aki", "@bot thanks")
STICKERS = (Sticker("ありがとう", "8515", "16581243"), Sticker("了解", "8515", "16581242"))


def send_sticker(stickers: tuple[Sticker, ...] = STICKERS) -> ClientTool:
    [tool] = sticker_tools(stickers)
    return tool


def run(tool_input: object, output: TurnOutput | None = None):
    output = output or TurnOutput()
    return send_sticker().run(tool_input, ToolTurn("Cg", MENTION, output)), output


def test_the_tool_offers_only_the_listed_names() -> None:
    definition = send_sticker().definition
    assert definition["name"] == "send_sticker"
    assert definition["input_schema"]["properties"]["name"]["enum"] == ["ありがとう", "了解"]


def test_no_stickers_means_no_tool() -> None:
    assert sticker_tools(()) == []


def test_a_named_sticker_is_added_with_its_record_line() -> None:
    outcome, output = run({"name": "ありがとう"})
    assert not outcome.is_error
    [extra] = output.extras
    assert extra.message == {"type": "sticker", "packageId": "8515", "stickerId": "16581243"}
    assert extra.record_line == "(スタンプ: ありがとう)"


@pytest.mark.parametrize(
    "tool_input", [{"name": "unknown"}, {}, {"name": None}, "ありがとう", None]
)
def test_a_name_outside_the_list_is_refused_with_the_names(tool_input: object) -> None:
    outcome, output = run(tool_input)
    assert outcome.is_error and "ありがとう, 了解" in outcome.content
    assert output.extras == []


def test_a_reply_carries_one_sticker() -> None:
    first, output = run({"name": "了解"})
    second, output = run({"name": "ありがとう"}, output)
    assert not first.is_error and second.is_error
    assert len(output.extras) == 1


def test_a_full_reply_takes_no_sticker() -> None:
    output = TurnOutput([OutgoingExtra({"type": "flex"}, "x")] * MAX_EXTRA_MESSAGES)
    outcome, output = run({"name": "了解"}, output)
    assert outcome.is_error and len(output.extras) == MAX_EXTRA_MESSAGES


def test_the_default_stickers_are_about_ten_with_distinct_names_and_ids() -> None:
    assert 8 <= len(DEFAULT_STICKERS) <= 15
    assert len({s.name for s in DEFAULT_STICKERS}) == len(DEFAULT_STICKERS)
    assert len({(s.package_id, s.sticker_id) for s in DEFAULT_STICKERS}) == len(DEFAULT_STICKERS)
    assert all(s.package_id.isdigit() and s.sticker_id.isdigit() for s in DEFAULT_STICKERS)
