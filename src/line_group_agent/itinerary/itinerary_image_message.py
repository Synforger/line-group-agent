"""Build the LINE image message that shows one image of an itinerary, and the line that
stands for it in the group's record.

Pure shape-building, no I/O; called by the itinerary tools.
"""

from __future__ import annotations

from typing import Any

from line_group_agent.itinerary.itinerary import Itinerary
from line_group_agent.itinerary.itinerary_message import CARD_TITLE

IMAGE_RECORD_LABEL = "[予定表の画像]"


def build_itinerary_image_message(url: str) -> dict[str, Any]:
    """Return an image message of the picture at `url` (https; LINE fetches it itself). The
    full image is its own preview: it is a few hundred KB, under LINE's 1 MB for a preview."""
    return {"type": "image", "originalContentUrl": url, "previewImageUrl": url}


def itinerary_image_record_line(itinerary: Itinerary) -> str:
    """Return `[予定表の画像] <title>`, the line that stands for an image in the group's
    record."""
    return f"{IMAGE_RECORD_LABEL} {itinerary.title or CARD_TITLE}"
