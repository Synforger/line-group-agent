"""Judge whether a web page is the page of a card, by its title.

Pure judgement, no I/O; called by the card image finder before a page's picture is given to
a card, so that a roundup or a list that merely mentions a place does not lend it its picture.
"""

from __future__ import annotations

import re
import unicodedata

MIN_NAME_CHARS = 2
# Text in brackets is often a tag such as 【人気】 rather than a reading, so it must be longer.
MIN_BRACKETED_NAME_CHARS = 3
_BRACKETED = re.compile(r"\(([^()]*)\)|【([^【】]*)】")
_WHITESPACE = re.compile(r"\s+")


def page_is_about(card_title: str, page_title: str | None) -> bool:
    """Return whether the page title holds the card's name: the card title without its
    brackets, or the text inside one of its brackets (a reading, for one), found anywhere in
    the page title. Both are compared in NFKC form, ignoring case and runs of spaces. A name
    of fewer than `MIN_NAME_CHARS` characters (`MIN_BRACKETED_NAME_CHARS` inside brackets) is
    not used, so a page without a title, or a card with no such name, never matches."""
    if not page_title:
        return False
    page = _normalized(page_title)
    return any(name in page for name in _names_of(card_title))


def _names_of(card_title: str) -> list[str]:
    title = _normalized(card_title)
    inside = [_normalized(a or b) for a, b in _BRACKETED.findall(title)]
    outside = _normalized(_BRACKETED.sub(" ", title))
    names = [outside] if len(outside) >= MIN_NAME_CHARS else []
    return names + [name for name in inside if len(name) >= MIN_BRACKETED_NAME_CHARS]


def _normalized(text: str) -> str:
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFKC", text).casefold()).strip()
