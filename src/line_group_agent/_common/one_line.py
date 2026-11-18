"""Make a value from the model fit a one-line field of a LINE message.

Pure functions; called by the cards, the poll cards, the location and the quick replies,
which all show short text the model wrote.
"""

from __future__ import annotations

import unicodedata

ELLIPSIS = "…"


def cut_with_ellipsis(value: str, limit: int) -> str:
    """Cut `value` to `limit` characters, ending in an ellipsis when it was cut."""
    if len(value) <= limit:
        return value
    return value[: limit - 1] + ELLIPSIS


def one_line(value: object, limit: int) -> str:
    """Return `value` as one line of at most `limit` characters: control characters are
    dropped, runs of white space become one space, and a longer text ends in an ellipsis.
    Anything that is not a string gives an empty line."""
    if not isinstance(value, str):
        return ""
    printable = "".join(c for c in value if c.isspace() or unicodedata.category(c) != "Cc")
    return cut_with_ellipsis(" ".join(printable.split()), limit)
