"""Turn Markdown the model may still write into plain text, because LINE shows none of it.

Pure functions; called by the answer sender just before a reply goes out (the text and
the cards' fields) and by the message redactor to match a bot reply with its record.
Only the marks LINE would show as stray characters are changed: heading hashes at the
start of a line, `**` around words, and `-` / `*` bullets at the start of a line.
"""

from __future__ import annotations

import re
from dataclasses import replace

from line_group_agent.cards.card import Card

HEADING_PATTERN = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
BULLET_PATTERN = re.compile(r"^([ \t]*)[-*][ \t]+", re.MULTILINE)
BOLD_MARK = "**"
BULLET = "・"


def to_plain_text(text: str) -> str:
    """Return `text` without heading hashes, `**` marks and bullet dashes."""
    without_headings = HEADING_PATTERN.sub("", text)
    without_bold = without_headings.replace(BOLD_MARK, "")
    return BULLET_PATTERN.sub(rf"\1{BULLET}", without_bold)


def to_plain_card(card: Card) -> Card:
    """Return the card with its title, text and price made plain."""
    return replace(
        card,
        title=to_plain_text(card.title),
        text=to_plain_text(card.text),
        price=None if card.price is None else to_plain_text(card.price),
    )
