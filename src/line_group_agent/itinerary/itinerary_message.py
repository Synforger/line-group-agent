"""Build the LINE Flex Message that shows an itinerary: the next three items and one button
that opens the itinerary's page.

Pure shape-building, no I/O; called by the itinerary tools.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from line_group_agent._common.one_line import cut_with_ellipsis
from line_group_agent.itinerary.itinerary import UNTIMED_LABEL, Itinerary, ItineraryItem
from line_group_agent.itinerary.itinerary_upcoming import upcoming_items
from line_group_agent.polls.poll_message import ALT_TEXT_MAX_CHARS, LIFF_BASE_URL

CARD_TITLE = "旅の予定表"
NO_ITEMS_LABEL = "まだ予定がありません"
OPEN_BUTTON_LABEL = "予定表を開く"
ITINERARY_RECORD_LABEL = "[予定表]"
SECONDARY_COLOR = "#666666"
ALT_TEXT_SEPARATOR = " / "


def liff_itinerary_url(liff_id: str, link_id: str) -> str:
    """Return the address that opens the page of the itinerary with this link id."""
    return f"{LIFF_BASE_URL}/{liff_id}/itinerary?i={link_id}"


def build_itinerary_message(itinerary: Itinerary, liff_id: str, now: datetime) -> dict[str, Any]:
    """Return one Flex Message object: the title, the next three items as of `now`, and the
    button to the page (the itinerary must have a link id)."""
    items = upcoming_items(itinerary, now)
    rows = [_row_of(itinerary, item) for item in items] or [_text(NO_ITEMS_LABEL, size="sm")]
    title = itinerary.title or CARD_TITLE
    alt_text = ALT_TEXT_SEPARATOR.join([title, *(item.title for item in items)])
    return {
        "type": "flex",
        "altText": cut_with_ellipsis(alt_text, ALT_TEXT_MAX_CHARS),
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "spacing": "md",
                "contents": [
                    _text(title, size="md", weight="bold"),
                    *rows,
                    {
                        "type": "button",
                        "style": "primary",
                        "height": "sm",
                        "margin": "md",
                        "action": {
                            "type": "uri",
                            "label": OPEN_BUTTON_LABEL,
                            "uri": liff_itinerary_url(liff_id, itinerary.link_id),
                        },
                    },
                ],
            },
        },
    }


def itinerary_record_line(itinerary: Itinerary) -> str:
    """Return `[予定表] <title> (<n>件)`, the line that stands for the card in the group's
    record."""
    return f"{ITINERARY_RECORD_LABEL} {itinerary.title or CARD_TITLE} ({len(itinerary.items)}件)"


def _row_of(itinerary: Itinerary, item: ItineraryItem) -> dict[str, Any]:
    day = itinerary.date_of_day(item.day)
    where = f"{day.month}/{day.day}" if day else f"{item.day}日目"
    when = f"{where} {item.start or UNTIMED_LABEL}"
    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "none",
        "contents": [
            _text(when, size="xs", color=SECONDARY_COLOR),
            _text(item.title, size="sm"),
        ],
    }


def _text(
    text: str, *, size: str, weight: str | None = None, color: str | None = None
) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text, "size": size, "wrap": True}
    if weight:
        node["weight"] = weight
    if color:
        node["color"] = color
    return node
