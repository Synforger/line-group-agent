"""The tool the model uses to show a place on a map in the group: a location message sent
after the reply text.

Called by the service builder, which adds the tool to the client tools.
"""

from __future__ import annotations

import math
from typing import Any

from line_group_agent._common.one_line import one_line
from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.media.location_record import location_line

SEND_LOCATION_TOOL_NAME = "send_location"
TITLE_MAX_CHARS = 100
ADDRESS_MAX_CHARS = 100
MAX_LATITUDE = 90.0
MAX_LONGITUDE = 180.0
ONE_PER_REPLY_RESULT = "A reply carries one location and this one already has it. Nothing was sent."
NO_ROOM_RESULT = "This reply already holds as many extra messages as LINE allows. Nothing was sent."
BAD_PLACE_RESULT = (
    "Give a title, an address, and a latitude (-90 to 90) and longitude (-180 to 180) as "
    "numbers. Nothing was sent."
)


def location_tools() -> list[ClientTool]:
    """Return the location tool."""
    return [ClientTool(SEND_LOCATION_TOOL_NAME, _definition(), _run)]


def _run(tool_input: object, turn: ToolTurn) -> ToolOutcome:
    fields = tool_input if isinstance(tool_input, dict) else {}
    title = one_line(fields.get("title"), TITLE_MAX_CHARS)
    address = one_line(fields.get("address"), ADDRESS_MAX_CHARS)
    latitude = _coordinate(fields.get("latitude"), MAX_LATITUDE)
    longitude = _coordinate(fields.get("longitude"), MAX_LONGITUDE)
    if not title or not address or latitude is None or longitude is None:
        return ToolOutcome(BAD_PLACE_RESULT, is_error=True)
    if turn.output.has_location():
        return ToolOutcome(ONE_PER_REPLY_RESULT, is_error=True)
    if not turn.output.has_room():
        return ToolOutcome(NO_ROOM_RESULT, is_error=True)
    message = {
        "type": "location",
        "title": title,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
    }
    turn.output.add(OutgoingExtra(message, location_line(title, address, latitude, longitude)))
    return ToolOutcome("The location is sent as a map message after your reply.")


def _coordinate(value: object, limit: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        return None
    return float(value) if abs(value) <= limit else None


def _definition() -> dict[str, Any]:
    return {
        "name": SEND_LOCATION_TOOL_NAME,
        "description": (
            "Show one place on a map in the group: a location message sent after your reply "
            "(members can tap it to open the map). Use it for a place you recommend or a "
            "meeting point, with the real address and coordinates; do not invent them. One "
            "location per reply. Write a short sentence inside <reply> too."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": f"Name of the place, up to {TITLE_MAX_CHARS} characters.",
                },
                "address": {
                    "type": "string",
                    "description": f"Its address, up to {ADDRESS_MAX_CHARS} characters.",
                },
                "latitude": {"type": "number", "description": "Latitude, -90 to 90."},
                "longitude": {"type": "number", "description": "Longitude, -180 to 180."},
            },
            "required": ["title", "address", "latitude", "longitude"],
        },
    }
