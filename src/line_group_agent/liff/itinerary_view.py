"""The shape of an itinerary as the page gets it: the trip, and for each day its items without
a fixed time and its timed items placed on an axis.

Pure shaping, no I/O; called by the LIFF itinerary service. Nothing about the group or its
members is in it; only the plan.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote

from line_group_agent.itinerary.itinerary import Itinerary, ItineraryItem
from line_group_agent.liff.day_layout import Band, layout_day

MAP_SEARCH_URL = "https://www.google.com/maps/search/?api=1&query="
WEB_URL_PATTERN = re.compile(r"^https?://\S+$")


def map_url_of(place: str) -> str:
    """Return the address of a map search for this place."""
    return MAP_SEARCH_URL + quote(place, safe="")


def itinerary_view_of(itinerary: Itinerary) -> dict[str, Any]:
    """Return the itinerary as JSON-ready values: one entry per day from day 1 to the last day
    that has an item (a day with nothing is there, empty)."""
    last_day = max((item.day for item in itinerary.items), default=0)
    day_date = [itinerary.date_of_day(day) for day in range(1, last_day + 1)]
    return {
        "title": itinerary.title,
        "start_date": itinerary.start_date,
        "legacy_text": itinerary.legacy_text,
        "days": [
            _day_view_of(
                itinerary, day, day_date[day - 1].isoformat() if day_date[day - 1] else None
            )
            for day in range(1, last_day + 1)
        ],
    }


def _day_view_of(itinerary: Itinerary, day: int, iso_date: str | None) -> dict[str, Any]:
    items = [item for item in itinerary.sorted_items() if item.day == day]
    layout = layout_day(items)
    return {
        "day": day,
        "label": itinerary.day_heading(day),
        "date": iso_date,
        "unscheduled": [_item_view_of(item) for item in items if item.start is None],
        "scheduled": [_band_view_of(band) for band in layout.bands] if layout else [],
        "axis": (
            {"start_min": layout.axis_start_min, "end_min": layout.axis_end_min} if layout else None
        ),
    }


def _item_view_of(item: ItineraryItem) -> dict[str, Any]:
    return {
        "title": item.title,
        "start": item.start,
        "end": item.end,
        "place": item.place,
        "map_url": map_url_of(item.place) if item.place else None,
        "note": item.note,
        "url": item.url if item.url and WEB_URL_PATTERN.match(item.url) else None,
    }


def _band_view_of(band: Band) -> dict[str, Any]:
    return _item_view_of(band.item) | {
        "start_min": band.start_min,
        "end_min": band.end_min,
        "bottom_min": band.bottom_min,
        "column": band.column,
        "columns": band.columns,
    }
