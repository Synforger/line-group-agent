from typing import Any

import pytest

from line_group_agent.agent.client_tool import ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.media.location_tools import location_tools
from line_group_agent.records.group_log import GroupMessage

MENTION = GroupMessage("t", "1", "U1", "Aki", "@bot where?")
[TOOL] = location_tools()
PLACE = {
    "title": "Gion Inn",
    "address": "Kyoto, Gion 1",
    "latitude": 35.0036,
    "longitude": 135.7756,
}


def run(tool_input: object, output: TurnOutput | None = None) -> tuple[ToolOutcome, TurnOutput]:
    output = output or TurnOutput()
    return TOOL.run(tool_input, ToolTurn("Cgroup", MENTION, output)), output


def test_the_place_becomes_a_location_message_and_a_record_line() -> None:
    outcome, output = run(PLACE)
    assert not outcome.is_error
    [extra] = output.extras
    assert extra.message == {"type": "location", **PLACE}
    assert extra.record_line == "[位置] Gion Inn Kyoto, Gion 1 (35.0036, 135.7756)"


def test_the_title_and_the_address_are_cut_to_what_LINE_takes() -> None:
    _, output = run({**PLACE, "title": "t" * 150, "address": "a\n" * 80})
    message = output.extras[0].message
    assert len(message["title"]) == 100 and len(message["address"]) == 100


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"address": " "},
        {"latitude": 91},
        {"latitude": -90.5},
        {"longitude": 180.1},
        {"latitude": "35"},
        {"latitude": True},
        {"longitude": float("nan")},
        {"longitude": None},
    ],
)
def test_a_place_without_a_name_or_real_coordinates_is_refused(changes: dict[str, Any]) -> None:
    outcome, output = run({**PLACE, **changes})
    assert outcome.is_error and output.extras == []


def test_the_edge_of_the_world_is_accepted() -> None:
    outcome, _ = run({**PLACE, "latitude": 90, "longitude": -180})
    assert not outcome.is_error


def test_a_reply_carries_one_location() -> None:
    output = TurnOutput()
    run(PLACE, output)
    outcome, _ = run({**PLACE, "title": "Other"}, output)
    assert outcome.is_error and len(output.extras) == 1


def test_a_reply_with_no_room_left_gets_no_location() -> None:
    output = TurnOutput()
    for _ in range(MAX_EXTRA_MESSAGES):
        output.add(OutgoingExtra({"type": "flex"}, "x"))
    outcome, _ = run(PLACE, output)
    assert outcome.is_error and len(output.extras) == MAX_EXTRA_MESSAGES


def test_a_call_without_input_is_refused() -> None:
    assert run(None)[0].is_error
