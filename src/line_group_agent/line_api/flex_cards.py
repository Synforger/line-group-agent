"""Build the LINE Flex Message (a carousel of bubbles) that shows a set of cards.

Pure shape-building, no I/O; called by the LINE client when it sends cards.
"""

from __future__ import annotations

from typing import Any

from line_group_agent._common.one_line import cut_with_ellipsis
from line_group_agent.cards.card import Card

ALT_TEXT_PREFIX = "候補: "
ALT_TEXT_SEPARATOR = " / "
ALT_TEXT_MAX_CHARS = 400
OPEN_BUTTON_LABEL = "開く"
IMAGE_ASPECT_RATIO = "20:13"
SECONDARY_COLOR = "#666666"


def build_flex_message(cards: list[Card], *, with_images: bool = True) -> dict[str, Any]:
    """Return one Flex Message object whose carousel holds a bubble per card.

    With `with_images` false the bubbles have no image block, which is the form
    that is tried again when LINE refuses a message that had images.
    """
    return {
        "type": "flex",
        "altText": alt_text_of(cards),
        "contents": {
            "type": "carousel",
            "contents": [_bubble(card, with_images=with_images) for card in cards],
        },
    }


def alt_text_of(cards: list[Card]) -> str:
    """Return the text shown in notifications and the talk list in place of the cards."""
    titles = ALT_TEXT_SEPARATOR.join(card.title for card in cards)
    return cut_with_ellipsis(f"{ALT_TEXT_PREFIX}{titles}", ALT_TEXT_MAX_CHARS)


def _bubble(card: Card, *, with_images: bool) -> dict[str, Any]:
    bubble: dict[str, Any] = {
        "type": "bubble",
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": _body_contents(card),
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "button",
                    "style": "primary",
                    "action": {"type": "uri", "label": OPEN_BUTTON_LABEL, "uri": card.url},
                }
            ],
        },
    }
    if with_images and card.image_url is not None:
        bubble["hero"] = {
            "type": "image",
            "url": card.image_url,
            "size": "full",
            "aspectRatio": IMAGE_ASPECT_RATIO,
            "aspectMode": "cover",
            "action": {"type": "uri", "uri": card.url},
        }
    return bubble


def _body_contents(card: Card) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = [
        {"type": "text", "text": card.title, "weight": "bold", "size": "md", "wrap": True}
    ]
    if card.price:
        contents.append({"type": "text", "text": card.price, "size": "sm", "wrap": True})
    if card.text:
        contents.append(
            {
                "type": "text",
                "text": card.text,
                "size": "sm",
                "color": SECONDARY_COLOR,
                "wrap": True,
            }
        )
    return contents
