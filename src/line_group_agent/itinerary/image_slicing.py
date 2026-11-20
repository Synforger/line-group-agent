"""Decide how the days of an itinerary image is cut into images: consecutive days go
together until an image would be taller than the limit, and no more than a few images are
made.

Pure calculation, no I/O; called by the itinerary renderer with the day blocks' positions
the page reports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ImageSlice:
    """One image: the page rows `top` to `bottom` (CSS pixels) holding `day_count` days."""

    top: float
    bottom: float
    day_count: int


def slice_days(
    blocks: Sequence[tuple[float, float]], *, max_height: float, max_count: int
) -> list[ImageSlice]:
    """Return the images that hold the days whose (top, bottom) rows are `blocks`, in order.

    The first image starts at the top of the page, so it carries the trip's title. A day
    taller than `max_height` is an image of its own. Days that do not fit in `max_count`
    images are left out (the sum of `day_count` tells how many were kept).
    """
    slices: list[ImageSlice] = []
    start = 0
    while start < len(blocks) and len(slices) < max_count:
        top = 0.0 if not slices else blocks[start][0]
        end = start + 1
        while end < len(blocks) and blocks[end][1] - top <= max_height:
            end += 1
        slices.append(ImageSlice(top, blocks[end - 1][1], end - start))
        start = end
    return slices
