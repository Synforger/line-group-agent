"""One candidate shown as a card in the group, and the limits every card is held to.

Built by `card_input.parse_cards` from the model's `show_cards` call; read by the
Flex Message builder and by the record text.
"""

from __future__ import annotations

from dataclasses import dataclass

# These sit below LINE's own limits (alt text 1500 characters, image URL 2000, button
# URI 10000, a carousel 12 bubbles / 50 KB), so a card that passes is one LINE accepts.
MAX_CARD_COUNT = 10
TITLE_MAX_CHARS = 40
TEXT_MAX_CHARS = 60
PRICE_MAX_CHARS = 20
URL_MAX_CHARS = 1000


@dataclass(frozen=True)
class Card:
    """A checked candidate: every field is already cut to its limit and every URL is
    an `https://` address."""

    title: str
    text: str
    url: str
    image_url: str | None = None
    price: str | None = None
