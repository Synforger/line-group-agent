"""Place the timed items of one day on a time axis: where each band starts and ends, which
column it takes when items overlap, and how far the axis reaches.

Pure calculation, no I/O; called by the itinerary view. Times are minutes since midnight.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from line_group_agent.itinerary.itinerary import MINUTES_PER_HOUR, ItineraryItem, minutes_of

MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR
DEFAULT_ITEM_MINUTES = MINUTES_PER_HOUR
# A band shorter than this is drawn this long, so its title can be read.
MIN_BAND_MINUTES = 30
AXIS_MARGIN_MINUTES = MINUTES_PER_HOUR
AXIS_STEP_MINUTES = 30


@dataclass(frozen=True)
class Band:
    """One timed item on the axis. `end_min` is the item's end (an hour after its start when
    it has none); `bottom_min` is where the band is drawn to. Items that overlap share the
    width: this one takes column `column` of `columns`."""

    item: ItineraryItem
    start_min: int
    end_min: int
    bottom_min: int
    column: int
    columns: int


@dataclass(frozen=True)
class DayLayout:
    """The bands of a day and the minutes the axis starts and ends at."""

    bands: list[Band]
    axis_start_min: int
    axis_end_min: int


def layout_day(items: Sequence[ItineraryItem]) -> DayLayout | None:
    """Return the layout of the items that have a start time, or None when none has. The axis
    starts an hour before the first item and ends an hour after the last, on a half hour line."""
    spans = sorted(
        (_span_of(item) for item in items if item.start is not None),
        key=lambda span: (span[1], span[3]),
    )
    if not spans:
        return None
    bands: list[Band] = []
    cluster: list[tuple[ItineraryItem, int, int, int]] = []
    cluster_bottom = 0
    for span in spans:
        if cluster and span[1] >= cluster_bottom:
            bands.extend(_bands_of(cluster))
            cluster = []
        cluster.append(span)
        cluster_bottom = max(cluster_bottom, span[3]) if len(cluster) > 1 else span[3]
    bands.extend(_bands_of(cluster))
    first = min(band.start_min for band in bands)
    last = max(band.bottom_min for band in bands)
    return DayLayout(
        bands,
        max(0, (first - AXIS_MARGIN_MINUTES) // AXIS_STEP_MINUTES * AXIS_STEP_MINUTES),
        min(
            MINUTES_PER_DAY,
            -(-(last + AXIS_MARGIN_MINUTES) // AXIS_STEP_MINUTES) * AXIS_STEP_MINUTES,
        ),
    )


def _span_of(item: ItineraryItem) -> tuple[ItineraryItem, int, int, int]:
    start = minutes_of(item.start or "00:00")
    end = minutes_of(item.end) if item.end else min(start + DEFAULT_ITEM_MINUTES, MINUTES_PER_DAY)
    return item, start, end, min(max(end, start + MIN_BAND_MINUTES), MINUTES_PER_DAY)


def _bands_of(cluster: list[tuple[ItineraryItem, int, int, int]]) -> list[Band]:
    """Give each item of a run of overlapping items the first column that is free at its start."""
    column_bottoms: list[int] = []
    placed: list[tuple[tuple[ItineraryItem, int, int, int], int]] = []
    for span in cluster:
        free = next((i for i, bottom in enumerate(column_bottoms) if bottom <= span[1]), None)
        if free is None:
            column_bottoms.append(span[3])
            free = len(column_bottoms) - 1
        else:
            column_bottoms[free] = span[3]
        placed.append((span, free))
    return [
        Band(item, start, end, bottom, column, len(column_bottoms))
        for (item, start, end, bottom), column in placed
    ]
