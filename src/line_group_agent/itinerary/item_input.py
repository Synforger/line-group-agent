"""Check and clean the fields of an itinerary item that come from the model (or from a file).

Pure functions that give back the clean value or raise `ItemInputError` with a sentence the
model can act on. Called by the itinerary tools and by the book when it reads a file.
"""

from __future__ import annotations

import re
from datetime import date

from line_group_agent._common.one_line import one_line
from line_group_agent.itinerary.itinerary import MAX_DAY

TITLE_MAX_CHARS = 60
PLACE_MAX_CHARS = 80
NOTE_MAX_CHARS = 300
URL_MAX_CHARS = 500
TRIP_TITLE_MAX_CHARS = 60
TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
URL_PATTERN = re.compile(r"^https?://\S+$")


class ItemInputError(ValueError):
    """A field that cannot be kept; the message says what to give instead."""


def day_of(raw: object) -> int:
    """Return the day number (1 is the first day of the trip), or refuse anything else."""
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= MAX_DAY:
        raise ItemInputError(f"day must be a whole number from 1 to {MAX_DAY}.")
    return raw


def time_of(raw: object, field: str) -> str | None:
    """Return a `HH:MM` time (an hour of one digit is padded), None for nothing or an empty
    string, or refuse anything else."""
    if raw is None or raw == "":
        return None
    match = TIME_PATTERN.match(raw.strip()) if isinstance(raw, str) else None
    if match is None:
        raise ItemInputError(f"{field} must be a 24-hour time like 09:30, or empty.")
    return f"{int(match.group(1)):02d}:{match.group(2)}"


def text_of(raw: object, field: str, limit: int, *, is_required: bool = False) -> str | None:
    """Return the text as one line, None for nothing or an empty string, or refuse a value
    that is not text, is missing when required, or is longer than `limit`."""
    if raw is None or raw == "":
        if is_required:
            raise ItemInputError(f"{field} is required.")
        return None
    if not isinstance(raw, str):
        raise ItemInputError(f"{field} must be text.")
    cleaned = one_line(raw, limit + 1)
    if len(cleaned) > limit:
        raise ItemInputError(f"{field} is over {limit} characters; shorten it.")
    if not cleaned:
        if is_required:
            raise ItemInputError(f"{field} is required.")
        return None
    return cleaned


def url_of(raw: object) -> str | None:
    """Return an `http` or `https` address, None for nothing or an empty string, or refuse
    anything else (a page opens only addresses of those two kinds)."""
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or not URL_PATTERN.match(raw.strip()):
        raise ItemInputError("url must start with http:// or https:// and hold no spaces.")
    if len(raw.strip()) > URL_MAX_CHARS:
        raise ItemInputError(f"url is over {URL_MAX_CHARS} characters.")
    return raw.strip()


def start_date_of(raw: object) -> str | None:
    """Return an ISO date (`2026-11-23`), None for nothing or an empty string, or refuse
    anything else."""
    if raw is None or raw == "":
        return None
    if not isinstance(raw, str) or not DATE_PATTERN.match(raw.strip()):
        raise ItemInputError("start_date must be a date like 2026-11-23, or empty.")
    try:
        date.fromisoformat(raw.strip())
    except ValueError as error:
        raise ItemInputError("start_date is not a real date.") from error
    return raw.strip()
