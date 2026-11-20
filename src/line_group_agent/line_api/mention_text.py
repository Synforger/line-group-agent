"""Turn the `<mention>name</mention>` marks in a reply into a LINE text message (v2) with real
mentions, or into the plain names when no mention can be made.

The model marks a member it names; LINE needs that member's user id in a `textV2` message
whose text holds a `{placeholder}` for each mention. A mark becomes a mention only when its
name is one of the names given (the group's record) and the message stays within LINE's limits;
any other mark is left as the bare name. Pure functions; called by the LINE client when it
builds a reply or a push.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MENTION_OPEN = "<mention>"
MENTION_CLOSE = "</mention>"
MENTION_PATTERN = re.compile(f"{re.escape(MENTION_OPEN)}(.*?){re.escape(MENTION_CLOSE)}", re.DOTALL)
# A message holds at most 20 mentions; the model may not call everyone.
MAX_MENTIONS = 20
EVERYONE_NAME = "all"
PLACEHOLDER_PREFIX = "m"
UTF16_BYTES_PER_UNIT = 2


@dataclass(frozen=True)
class TextV2:
    """The `text` and `substitution` of a `textV2` message."""

    text: str
    substitution: dict[str, Any]


def has_mention_marks(text: str) -> bool:
    """Return whether the text holds a mention mark."""
    return MENTION_OPEN in text


def strip_mention_marks(text: str) -> str:
    """Return the text with each mark replaced by the name inside it (and any stray tag
    removed)."""
    return _without_tags(MENTION_PATTERN.sub(_name_of, text))


def build_text_v2(
    text: str, mentionable: Mapping[str, str], *, limit_utf16_units: int
) -> TextV2 | None:
    """Return the `textV2` form of the text with each mark whose name is a key of `mentionable`
    (name to user id) made a mention, or None when no mark became one or the result is
    longer than `limit_utf16_units` (a cut text could end inside a placeholder).

    A literal `{` or `}` is doubled, as `textV2` requires.
    """
    substitution: dict[str, Any] = {}
    parts: list[str] = []
    cursor = 0
    for found in MENTION_PATTERN.finditer(text):
        parts.append(_escaped(_without_tags(text[cursor : found.start()])))
        cursor = found.end()
        name = _name_of(found)
        user_id = mentionable.get(name)
        if user_id is None or name.casefold() == EVERYONE_NAME or len(substitution) >= MAX_MENTIONS:
            parts.append(_escaped(name))
            continue
        key = f"{PLACEHOLDER_PREFIX}{len(substitution) + 1}"
        substitution[key] = {"type": "mention", "mentionee": {"type": "user", "userId": user_id}}
        parts.append(f"{{{key}}}")
    parts.append(_escaped(_without_tags(text[cursor:])))
    if not substitution:
        return None
    body = "".join(parts)
    if len(body.encode("utf-16-le")) > limit_utf16_units * UTF16_BYTES_PER_UNIT:
        return None
    return TextV2(body, substitution)


def _name_of(found: re.Match[str]) -> str:
    """Return the name a mark holds, without the spaces around it."""
    return found.group(1).strip()


def _without_tags(text: str) -> str:
    return text.replace(MENTION_OPEN, "").replace(MENTION_CLOSE, "")


def _escaped(text: str) -> str:
    return text.replace("{", "{{").replace("}", "}}")
