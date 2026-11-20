"""The line that stands for a sticker in the group's record: `(スタンプ: <words>)`.

Used for a sticker a member sends (its keywords, as LINE gives them) and for one the bot
sends (its name), so a later mention can see both. Pure text building; called by the event
dispatcher and the sticker tool.
"""

from __future__ import annotations

from typing import Any

from line_group_agent._common.one_line import one_line

STICKER_RECORD_LABEL = "(スタンプ"
KEYWORD_SEPARATOR = "、"
KEYWORDS_MAX_CHARS = 100


def sticker_line(words: str) -> str:
    """Return `(スタンプ: words)`, or `(スタンプ)` when there is nothing to say about it."""
    return f"{STICKER_RECORD_LABEL}: {words})" if words else f"{STICKER_RECORD_LABEL})"


def received_sticker_line(message: dict[str, Any]) -> str:
    """Return the record line for a sticker message a member sent: its keywords joined by
    `、`, kept to one line."""
    keywords = message.get("keywords")
    if not isinstance(keywords, list):
        return sticker_line("")
    words = (one_line(keyword, KEYWORDS_MAX_CHARS) for keyword in keywords)
    return sticker_line(one_line(KEYWORD_SEPARATOR.join(w for w in words if w), KEYWORDS_MAX_CHARS))
