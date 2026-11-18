"""Build the LINE Flex Message that shows a poll: the question and one button per option.

A button sends a postback (not a chat message), so a vote is silent in the group; the data
holds the poll id and the option's place. Pure shape-building, no I/O; called by the poll
tools.
"""

from __future__ import annotations

from typing import Any

from line_group_agent._common.one_line import cut_with_ellipsis
from line_group_agent.polls.poll import KIND_DATE, Poll

POSTBACK_PREFIX = "poll"
POSTBACK_SEPARATOR = ":"
ALT_TEXT_MAX_CHARS = 400
QUESTION_MAX_CHARS = 100
OPTION_MAX_CHARS = 20
CHOICE_HINT = "1人1票。もう一度押すと取り消し"
MULTIPLE_HINT = "複数選べます。もう一度押すと取り消し"
DATE_HINT = "大丈夫な日を押してください(複数可)。もう一度押すと取り消し"
SECONDARY_COLOR = "#666666"


def postback_data_of(poll_id: str, option_index: int) -> str:
    """Return the data a button carries: `poll:<id>:<option index>` (well under LINE's 300)."""
    return POSTBACK_SEPARATOR.join((POSTBACK_PREFIX, poll_id, str(option_index)))


def build_poll_message(poll: Poll) -> dict[str, Any]:
    """Return one Flex Message object holding the poll."""
    return {
        "type": "flex",
        "altText": cut_with_ellipsis(f"{_hint_of(poll)}: {poll.question}", ALT_TEXT_MAX_CHARS),
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "sm",
                "contents": [
                    {
                        "type": "text",
                        "text": poll.question,
                        "weight": "bold",
                        "size": "md",
                        "wrap": True,
                    },
                    {
                        "type": "text",
                        "text": _hint_of(poll),
                        "size": "xs",
                        "color": SECONDARY_COLOR,
                        "wrap": True,
                    },
                    *[_button(poll, index) for index in range(len(poll.options))],
                ],
            },
        },
    }


def _button(poll: Poll, index: int) -> dict[str, Any]:
    return {
        "type": "button",
        "style": "secondary",
        "height": "sm",
        "action": {
            "type": "postback",
            "label": cut_with_ellipsis(poll.options[index].label, OPTION_MAX_CHARS),
            "data": postback_data_of(poll.id, index),
        },
    }


def _hint_of(poll: Poll) -> str:
    if poll.kind == KIND_DATE:
        return DATE_HINT
    return MULTIPLE_HINT if poll.multiple else CHOICE_HINT
