"""The line that stands for sent cards in the group's record.

The record holds text only, so cards are written after the reply text; a later
mention such as "the second one" can then be matched to a name and an address.
Called by the event dispatcher.
"""

from __future__ import annotations

from line_group_agent.cards.card import Card

CARD_RECORD_LABEL = "[カード]"
ENTRY_SEPARATOR = " / "


def format_card_record(cards: list[Card]) -> str:
    """Return `[カード] 1. name (price) url / 2. …` for the cards, in order."""
    entries = []
    for number, card in enumerate(cards, start=1):
        price = f" ({card.price})" if card.price else ""
        entries.append(f"{number}. {card.title}{price} {card.url}")
    return f"{CARD_RECORD_LABEL} {ENTRY_SEPARATOR.join(entries)}"
