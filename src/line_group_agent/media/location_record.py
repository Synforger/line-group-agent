"""The line that stands for a location in the group's record: `[位置] name address (lat, lon)`.

Used for a location a member shares and for one the bot sends, so a later mention can see
both. Pure text building; called by the event dispatcher and the location tool.
"""

from __future__ import annotations

from typing import Any

LOCATION_RECORD_LABEL = "[位置]"
COORDINATE_DIGITS = 6


def location_line(title: str, address: str, latitude: float, longitude: float) -> str:
    """Return `[位置] title address (lat, lon)`; an empty title or address is left out."""
    named = " ".join(part for part in (LOCATION_RECORD_LABEL, title, address) if part)
    return f"{named} ({_rounded(latitude)}, {_rounded(longitude)})"


def shared_location_line(message: dict[str, Any]) -> str | None:
    """Return the record line for a location message a member sent, or None when it holds
    no coordinates."""
    latitude, longitude = message.get("latitude"), message.get("longitude")
    if not (_is_number(latitude) and _is_number(longitude)):
        return None
    title, address = message.get("title"), message.get("address")
    return location_line(
        title.strip() if isinstance(title, str) else "",
        address.strip() if isinstance(address, str) else "",
        latitude,
        longitude,
    )


def _rounded(value: float) -> float:
    return round(value, COORDINATE_DIGITS)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)
