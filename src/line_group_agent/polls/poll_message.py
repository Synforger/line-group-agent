"""Build the LINE Flex Message that shows a poll: the question and one button per option.

A button sends a postback (not a chat message); the data holds the poll id and the option's
place. In a one-pick poll the button also carries a display text, so LINE shows "<option> に投票"
in the talk as a message of the member who pressed it. In a poll that allows several picks the
agent answers each press with one line instead (see the postback handler).

With a LIFF app configured the card has no option buttons: it lists the options with their
counts and has one button that opens the voting page (`liff_poll_url`), where a press shows
nothing in the talk. Pure shape-building, no I/O; called by the poll tools.
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
# LINE's limit for a postback action's display text.
DISPLAY_TEXT_MAX_CHARS = 300
DISPLAY_TEXT_SUFFIX = " に投票"
CHOICE_HINT = "1人1票。別の選択肢を押すと選び直せます"
MULTIPLE_HINT = "複数選べます。もう一度押すと取り消し"
DATE_HINT = "大丈夫な日を押してください(複数可)。もう一度押すと取り消し"
SECONDARY_COLOR = "#666666"
LIFF_BUTTON_LABEL = "開いて投票"
LIFF_BASE_URL = "https://liff.line.me"
VOTE_COUNT_SUFFIX = "票"


def postback_data_of(poll_id: str, option_index: int) -> str:
    """Return the data a button carries: `poll:<id>:<option index>` (well under LINE's 300)."""
    return POSTBACK_SEPARATOR.join((POSTBACK_PREFIX, poll_id, str(option_index)))


def liff_poll_url(liff_id: str, link_id: str) -> str:
    """Return the address that opens the voting page of the poll with this link id."""
    return f"{LIFF_BASE_URL}/{liff_id}?p={link_id}"


def build_poll_message(poll: Poll, *, liff_id: str | None = None) -> dict[str, Any]:
    """Return one Flex Message object holding the poll: a postback button per option, or,
    with `liff_id` and a poll that has a link id, the counts and one button to the voting page."""
    if liff_id is not None and poll.link_id:
        entries = [*_counts(poll), _page_button(liff_poll_url(liff_id, poll.link_id))]
    else:
        entries = [_button(poll, index) for index in range(len(poll.options))]
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
                    *entries,
                ],
            },
        },
    }


def _counts(poll: Poll) -> list[dict[str, Any]]:
    return [
        {
            "type": "text",
            "text": f"{number}. {option.label}: {len(option.voters)}{VOTE_COUNT_SUFFIX}",
            "size": "sm",
            "wrap": True,
        }
        for number, option in enumerate(poll.options, start=1)
    ]


def _page_button(url: str) -> dict[str, Any]:
    return {
        "type": "button",
        "style": "primary",
        "height": "sm",
        "margin": "md",
        "action": {"type": "uri", "label": LIFF_BUTTON_LABEL, "uri": url},
    }


def _button(poll: Poll, index: int) -> dict[str, Any]:
    label = poll.options[index].label
    action = {
        "type": "postback",
        "label": cut_with_ellipsis(label, OPTION_MAX_CHARS),
        "data": postback_data_of(poll.id, index),
    }
    if poll.kind != KIND_DATE and not poll.multiple:
        action["displayText"] = cut_with_ellipsis(
            f"{label}{DISPLAY_TEXT_SUFFIX}", DISPLAY_TEXT_MAX_CHARS
        )
    return {"type": "button", "style": "secondary", "height": "sm", "action": action}


def _hint_of(poll: Poll) -> str:
    if poll.kind == KIND_DATE:
        return DATE_HINT
    return MULTIPLE_HINT if poll.multiple else CHOICE_HINT
