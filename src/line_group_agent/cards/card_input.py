"""Check what the model passed to `show_cards` and turn it into cards.

Pure judgement, no I/O; called by the answerer.
"""

from __future__ import annotations

import unicodedata
from urllib.parse import quote, urlsplit

from line_group_agent.cards.card import (
    MAX_CARD_COUNT,
    PRICE_MAX_CHARS,
    TEXT_MAX_CHARS,
    TITLE_MAX_CHARS,
    URL_MAX_CHARS,
    Card,
)

ELLIPSIS = "…"
HTTPS_PREFIX = "https://"


def parse_cards(raw_input: object) -> list[Card]:
    """Return the valid cards of a `show_cards` input, at most `MAX_CARD_COUNT`.

    A card whose `url` is not usable is dropped. A card whose `image_url` is not
    usable loses its image only. Long text is cut with a trailing ellipsis.
    """
    if not isinstance(raw_input, dict):
        return []
    items = raw_input.get("cards")
    if not isinstance(items, list):
        return []
    cards: list[Card] = []
    for item in items:
        card = _parse_card(item)
        if card is not None:
            cards.append(card)
        if len(cards) == MAX_CARD_COUNT:
            break
    return cards


def cut_with_ellipsis(value: str, limit: int) -> str:
    """Cut `value` to `limit` characters, ending in an ellipsis when it was cut."""
    if len(value) <= limit:
        return value
    return value[: limit - 1] + ELLIPSIS


def _parse_card(item: object) -> Card | None:
    if not isinstance(item, dict):
        return None
    url = _usable_url(item.get("url"))
    title = _one_line(item.get("title"), TITLE_MAX_CHARS)
    if url is None or not title:
        return None
    return Card(
        title=title,
        text=_one_line(item.get("text"), TEXT_MAX_CHARS),
        url=url,
        image_url=_usable_url(item.get("image_url")),
        price=_one_line(item.get("price"), PRICE_MAX_CHARS) or None,
    )


def _one_line(value: object, limit: int) -> str:
    if not isinstance(value, str):
        return ""
    printable = "".join(c for c in value if c.isspace() or unicodedata.category(c) != "Cc")
    return cut_with_ellipsis(" ".join(printable.split()), limit)


def _usable_url(value: object) -> str | None:
    """Return the address as LINE wants it (non-ASCII percent-encoded), or None."""
    if not isinstance(value, str):
        return None
    url = value.strip()
    if any(c.isspace() or unicodedata.category(c) == "Cc" for c in url):
        return None
    url = "".join(c if c.isascii() else quote(c, safe="") for c in url)
    if not url.startswith(HTTPS_PREFIX) or len(url) > URL_MAX_CHARS:
        return None
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return None
    return url if host else None
