"""Check what the model passed to `show_cards` and turn it into cards.

Pure judgement, no I/O (the only trace it leaves is a count in the log); called by the answerer
and, for the shape of an address, by the card image finder.
"""

from __future__ import annotations

import logging
import unicodedata
from urllib.parse import quote, urlsplit

from line_group_agent._common.one_line import one_line
from line_group_agent.cards.card import (
    MAX_CARD_COUNT,
    PRICE_MAX_CHARS,
    TEXT_MAX_CHARS,
    TITLE_MAX_CHARS,
    URL_MAX_CHARS,
    Card,
)

logger = logging.getLogger(__name__)

HTTPS_PREFIX = "https://"


def parse_cards(raw_input: object) -> list[Card]:
    """Return the valid cards of a `show_cards` input, at most `MAX_CARD_COUNT`.

    A card whose `url` is not usable is dropped. A card whose `url` an earlier card already
    has is dropped too (each card must be its own page). A card whose `image_url` is not
    usable loses its image only. Long text is cut with a trailing ellipsis.
    """
    if not isinstance(raw_input, dict):
        return []
    items = raw_input.get("cards")
    if not isinstance(items, list):
        return []
    cards: list[Card] = []
    seen_urls: set[str] = set()
    repeated_count = 0
    for item in items:
        card = _parse_card(item)
        if card is not None and card.url in seen_urls:
            repeated_count += 1
        elif card is not None:
            cards.append(card)
            seen_urls.add(card.url)
        if len(cards) == MAX_CARD_COUNT:
            break
    if repeated_count:
        logger.info(
            "cards: dropped %d card(s) whose url an earlier card already has", repeated_count
        )
    return cards


def _parse_card(item: object) -> Card | None:
    if not isinstance(item, dict):
        return None
    url = usable_https_url(item.get("url"))
    title = one_line(item.get("title"), TITLE_MAX_CHARS)
    if url is None or not title:
        return None
    return Card(
        title=title,
        text=one_line(item.get("text"), TEXT_MAX_CHARS),
        url=url,
        image_url=usable_https_url(item.get("image_url")),
        price=one_line(item.get("price"), PRICE_MAX_CHARS) or None,
    )


def usable_https_url(value: object) -> str | None:
    """Return the address as LINE wants it (non-ASCII percent-encoded), or None unless it is
    an `https://` address of at most `URL_MAX_CHARS` characters that names a host."""
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
