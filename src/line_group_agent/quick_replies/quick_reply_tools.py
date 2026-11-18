"""The tool the model uses to offer tap-to-answer buttons under its reply.

LINE shows quick reply buttons under the last message of the reply; tapping one sends a
message from the member. When the bot has a call name, that message starts with it
(`Sora、Kyoto`), so tapping calls the bot like a typed mention would. Called by the service
builder, which adds the tool to the client tools.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from line_group_agent._common.one_line import cut_with_ellipsis, one_line
from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.line_api.quick_reply import LABEL_MAX_CHARS, TEXT_MAX_CHARS, QuickReplyItem

SUGGEST_REPLIES_TOOL_NAME = "suggest_replies"
MIN_OPTION_COUNT = 1
MAX_OPTION_COUNT = 5
CALL_SEPARATOR = "、"
BAD_OPTIONS_RESULT = (
    f"Give {MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} short, non-empty options. "
    "No buttons were added."
)


def quick_reply_tools(call_name: str | None) -> list[ClientTool]:
    """Return the quick reply tool; `call_name` is the name a tap addresses the bot by (None
    when the bot has none, and a tap then sends the option alone)."""

    def suggest(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        raw = tool_input.get("options") if isinstance(tool_input, dict) else None
        options = _clean(raw)
        if options is None:
            return ToolOutcome(BAD_OPTIONS_RESULT, is_error=True)
        turn.output.quick_replies[:] = [_item(option, call_name) for option in options]
        return ToolOutcome(
            f"{len(options)} button(s) will be shown under your reply. A member taps one to "
            "answer; their answer reaches you as a message."
        )

    return [ClientTool(SUGGEST_REPLIES_TOOL_NAME, _definition(), suggest)]


def _clean(raw: object) -> list[str] | None:
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        return None
    options: list[str] = []
    for item in raw:
        option = one_line(item, TEXT_MAX_CHARS)
        if not option:
            return None
        if option not in options:
            options.append(option)
    return options if MIN_OPTION_COUNT <= len(options) <= MAX_OPTION_COUNT else None


def _item(option: str, call_name: str | None) -> QuickReplyItem:
    text = option if call_name is None else f"{call_name}{CALL_SEPARATOR}{option}"
    return QuickReplyItem(
        label=cut_with_ellipsis(option, LABEL_MAX_CHARS),
        text=cut_with_ellipsis(text, TEXT_MAX_CHARS),
    )


def _definition() -> dict[str, Any]:
    return {
        "name": SUGGEST_REPLIES_TOOL_NAME,
        "description": (
            "Show tap-to-answer buttons under your reply, for a question members can answer "
            "with one tap (yes/no, a choice between a few things). A tap sends that option "
            "as the member's message to you. Give 1 to "
            f"{MAX_OPTION_COUNT} short options (up to {LABEL_MAX_CHARS} characters each show "
            "in full). The buttons go away after one is tapped or when someone else writes. "
            "Ask the question inside <reply> too."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"{MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} short options.",
                },
            },
            "required": ["options"],
        },
    }
