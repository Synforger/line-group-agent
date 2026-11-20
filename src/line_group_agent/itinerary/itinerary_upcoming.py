"""Pick the next few items of an itinerary: those not over yet, as of a moment.

Pure judgement, no I/O; called by the itinerary card.
"""

from __future__ import annotations

from datetime import datetime

from line_group_agent.itinerary.itinerary import (
    MINUTES_PER_HOUR,
    Itinerary,
    ItineraryItem,
    minutes_of,
)

UPCOMING_COUNT = 3


def upcoming_items(itinerary: Itinerary, now: datetime) -> list[ItineraryItem]:
    """Return the next three items in the order of the trip. An item is over once its end
    time (an hour after its start when it has no end) has passed; an item without a time is
    over when its day is. Without a first day nothing can be over, so the first three are
    returned; when the whole trip is over, the last three."""
    ordered = itinerary.sorted_items()
    if itinerary.start_date is None:
        return ordered[:UPCOMING_COUNT]
    left = [item for item in ordered if not _is_over(itinerary, item, now)]
    return left[:UPCOMING_COUNT] if left else ordered[-UPCOMING_COUNT:]


def _is_over(itinerary: Itinerary, item: ItineraryItem, now: datetime) -> bool:
    day = itinerary.date_of_day(item.day)
    if day is None:
        return False
    if day != now.date():
        return day < now.date()
    if item.start is None:
        return False
    end = minutes_of(item.end) if item.end else minutes_of(item.start) + MINUTES_PER_HOUR
    return end <= now.hour * MINUTES_PER_HOUR + now.minute
