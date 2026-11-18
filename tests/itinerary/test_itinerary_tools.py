from datetime import datetime
from pathlib import Path

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.itinerary.itinerary_tools import (
    ITINERARY_MAX_CHARS,
    NO_ITINERARY_RESULT,
    itinerary_tools,
)
from line_group_agent.records.group_log import GroupMessage

GROUP = "Cgroup"
MENTION = GroupMessage("t", "1", "U1", "Aki", "@bot plan")


def setup(tmp_path: Path) -> tuple[dict[str, ClientTool], ItineraryBook]:
    book = ItineraryBook(tmp_path, lambda: datetime(2026, 11, 18, 12, 0).astimezone())
    return {tool.name: tool for tool in itinerary_tools(book)}, book


def run(tool: ClientTool, tool_input: object) -> ToolOutcome:
    return tool.run(tool_input, ToolTurn(GROUP, MENTION, TurnOutput()))


def test_get_says_so_when_nothing_is_saved(tmp_path: Path) -> None:
    tools, _ = setup(tmp_path)
    assert run(tools["get_itinerary"], {}).content == NO_ITINERARY_RESULT


def test_update_replaces_the_whole_text_and_get_returns_it(tmp_path: Path) -> None:
    tools, book = setup(tmp_path)
    assert not run(tools["update_itinerary"], {"text": "  1日目 (11/23)\nKyoto \n"}).is_error
    assert book.get(GROUP) is not None
    content = run(tools["get_itinerary"], {}).content
    assert content.endswith("\n1日目 (11/23)\nKyoto")
    run(tools["update_itinerary"], {"text": "1日目 (11/23)\nOsaka"})
    assert [v.text for v in book.versions(GROUP)] == ["1日目 (11/23)\nKyoto"]


def test_update_refuses_an_empty_or_missing_text(tmp_path: Path) -> None:
    tools, book = setup(tmp_path)
    for tool_input in ({"text": "  "}, {}, None, {"text": 3}):
        assert run(tools["update_itinerary"], tool_input).is_error
    assert book.get(GROUP) is None


def test_update_refuses_a_text_longer_than_a_message(tmp_path: Path) -> None:
    tools, book = setup(tmp_path)
    outcome = run(tools["update_itinerary"], {"text": "x" * (ITINERARY_MAX_CHARS + 1)})
    assert outcome.is_error and book.get(GROUP) is None
    assert not run(tools["update_itinerary"], {"text": "x" * ITINERARY_MAX_CHARS}).is_error


def test_saving_the_same_text_is_not_an_error_but_changes_nothing(tmp_path: Path) -> None:
    tools, book = setup(tmp_path)
    run(tools["update_itinerary"], {"text": "same"})
    outcome = run(tools["update_itinerary"], {"text": "same"})
    assert not outcome.is_error and "nothing changed" in outcome.content
    assert book.versions(GROUP) == []
