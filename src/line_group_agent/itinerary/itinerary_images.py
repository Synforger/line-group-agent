"""Make the images of a group's itinerary and give their public addresses: draw them, keep
them in the group's folder and name each by `<public_base_url>/liff/media/<id>.png`.

Drawing takes seconds, so `create` is async and the agent handles other events while it waits.
Called by the itinerary tools; the store is also read by the LIFF router that serves the
addresses.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from line_group_agent.itinerary.itinerary import Itinerary
from line_group_agent.itinerary.itinerary_image_store import ItineraryImageStore
from line_group_agent.itinerary.itinerary_renderer import ItineraryRenderer
from line_group_agent.liff.itinerary_view import itinerary_view_of

MEDIA_PATH = "/liff/media/"
DRAW_WAIT_SECONDS = 45

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ItineraryImageSet:
    """The addresses of the drawn images, in order, and how many days did not fit them."""

    urls: list[str]
    omitted_day_count: int


class ItineraryImages:
    """Draws an itinerary into images that LINE can fetch."""

    def __init__(
        self, renderer: ItineraryRenderer, store: ItineraryImageStore, *, public_base_url: str
    ) -> None:
        self.renderer = renderer
        self.store = store
        self.public_base_url = public_base_url
        self._one_drawing_at_a_time = asyncio.Lock()

    async def create(self, group_id: str, itinerary: Itinerary) -> ItineraryImageSet | None:
        """Draw the itinerary (it must hold an item), keep the images and return their
        addresses; return None, after a log line, when the images could not be made. One
        drawing runs at a time."""
        try:
            async with self._one_drawing_at_a_time, asyncio.timeout(DRAW_WAIT_SECONDS):
                rendered = await self.renderer.render(itinerary_view_of(itinerary))
                names = [self.store.save(group_id, png) for png in rendered.images]
        except TimeoutError:
            logger.warning("itinerary images: drawing took longer than %ds", DRAW_WAIT_SECONDS)
            return None
        except Exception as error:  # nothing in drawing may end the answer; the card replaces it
            logger.warning("itinerary images: could not draw (%s)", error)
            return None
        urls = [f"{self.public_base_url}{MEDIA_PATH}{name}" for name in names]
        return ItineraryImageSet(urls, rendered.omitted_day_count)
