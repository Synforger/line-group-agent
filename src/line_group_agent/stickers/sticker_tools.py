"""The tool the model uses to send a sticker in the group: a sticker message sent after the
reply text.

Called by the service builder, which adds the tool to the client tools.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.stickers.sticker import Sticker
from line_group_agent.stickers.sticker_record import sticker_line

SEND_STICKER_TOOL_NAME = "send_sticker"
STICKER_TYPE = "sticker"
ONE_PER_REPLY_RESULT = "A reply carries one sticker and this one already has it. Nothing was sent."
NO_ROOM_RESULT = "This reply already holds as many extra messages as LINE allows. Nothing was sent."
SENT_RESULT = "The sticker is sent after your reply."


def sticker_tools(stickers: Sequence[Sticker]) -> list[ClientTool]:
    """Return the sticker tool, or none when there is no sticker to send."""
    if not stickers:
        return []
    by_name = {sticker.name: sticker for sticker in stickers}

    def run(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        sticker = by_name.get(str(fields.get("name")))
        if sticker is None:
            return ToolOutcome(_unknown_name_result(list(by_name)), is_error=True)
        if any(extra.message.get("type") == STICKER_TYPE for extra in turn.output.extras):
            return ToolOutcome(ONE_PER_REPLY_RESULT, is_error=True)
        if not turn.output.has_room():
            return ToolOutcome(NO_ROOM_RESULT, is_error=True)
        message = {
            "type": STICKER_TYPE,
            "packageId": sticker.package_id,
            "stickerId": sticker.sticker_id,
        }
        turn.output.add(OutgoingExtra(message, sticker_line(sticker.name)))
        return ToolOutcome(SENT_RESULT)

    return [ClientTool(SEND_STICKER_TOOL_NAME, _definition(list(by_name)), run)]


def _unknown_name_result(names: list[str]) -> str:
    return f"No sticker has that name. Pick one of: {', '.join(names)}. Nothing was sent."


def _definition(names: list[str]) -> dict[str, Any]:
    return {
        "name": SEND_STICKER_TOOL_NAME,
        "description": (
            "Send one LINE sticker to the group after your reply. Use it only when it "
            "lightens the mood (thanks, congratulations, an apology, a laugh), not in every "
            "reply and never instead of an answer. One sticker per reply. Write a short "
            "sentence inside <reply> too."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "enum": names,
                    "description": "The sticker to send.",
                },
            },
            "required": ["name"],
            "additionalProperties": False,
        },
    }
