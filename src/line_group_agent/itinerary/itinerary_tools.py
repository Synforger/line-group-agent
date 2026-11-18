"""The tools the model uses to read and replace the group's trip itinerary.

The itinerary is plain text; each day starts with a heading line such as `1日目 (11/23)`.
A member who mentions the bot with only the itinerary keyword gets the saved text back
without the model (the event dispatcher does that). Called by the service builder, which
adds the tools to the client tools.
"""

from __future__ import annotations

from typing import Any

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.itinerary.itinerary_book import ItineraryBook

GET_ITINERARY_TOOL_NAME = "get_itinerary"
UPDATE_ITINERARY_TOOL_NAME = "update_itinerary"
ITINERARY_MAX_CHARS = 4000
NO_ITINERARY_RESULT = "No itinerary is saved for this group yet."
EMPTY_TEXT_RESULT = "Give the whole new itinerary as text; nothing was saved."
TOO_LONG_RESULT = (
    f"The itinerary is over {ITINERARY_MAX_CHARS} characters, more than a LINE message can "
    "hold. Shorten it and call update_itinerary again; nothing was saved."
)


def itinerary_tools(book: ItineraryBook) -> list[ClientTool]:
    """Return the itinerary tools, working on `book`."""

    def get(_tool_input: object, turn: ToolTurn) -> ToolOutcome:
        itinerary = book.get(turn.group_id)
        if itinerary is None:
            return ToolOutcome(NO_ITINERARY_RESULT)
        return ToolOutcome(f"Saved {itinerary.saved_at}:\n{itinerary.text}")

    def update(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        raw = tool_input.get("text") if isinstance(tool_input, dict) else None
        text = raw.strip() if isinstance(raw, str) else ""
        if not text:
            return ToolOutcome(EMPTY_TEXT_RESULT, is_error=True)
        if len(text) > ITINERARY_MAX_CHARS:
            return ToolOutcome(TOO_LONG_RESULT, is_error=True)
        if not book.update(turn.group_id, text):
            return ToolOutcome("That is already the saved itinerary; nothing changed.")
        return ToolOutcome("The itinerary is saved. The earlier version is kept.")

    return [
        ClientTool(GET_ITINERARY_TOOL_NAME, _get_definition(), get),
        ClientTool(UPDATE_ITINERARY_TOOL_NAME, _update_definition(), update),
    ]


def _get_definition() -> dict[str, Any]:
    return {
        "name": GET_ITINERARY_TOOL_NAME,
        "description": (
            "Read the group's saved trip itinerary (plain text). Call it before you change "
            "the itinerary, and when a member asks what the plan is."
        ),
        "input_schema": {"type": "object", "properties": {}},
    }


def _update_definition() -> dict[str, Any]:
    return {
        "name": UPDATE_ITINERARY_TOOL_NAME,
        "description": (
            "Replace the group's whole trip itinerary by the text you give, so write the "
            "full new itinerary, not only the change (read the old one with get_itinerary "
            "first). Plain text, no Markdown. Start each day with a heading line like "
            f"'1日目 (11/23)'. Up to {ITINERARY_MAX_CHARS} characters. The earlier version is "
            "kept. Save only what the members decided or asked you to write."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The whole itinerary."},
            },
            "required": ["text"],
        },
    }
