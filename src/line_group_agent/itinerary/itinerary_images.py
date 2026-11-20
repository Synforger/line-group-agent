"""Make the images of a group's itinerary and give their public addresses: draw them, keep
them in the group's folder and name each by `<public_base_url>/liff/media/<id>.png`.

The itinerary tool runs inside the agent's event loop and is not async, so `create_blocking`
draws on a worker thread and waits for it. Called by the itinerary tools; the store is also
read by the LIFF router that serves the addresses.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
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
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="itinerary-image")

    async def create(self, group_id: str, itinerary: Itinerary) -> ItineraryImageSet:
        """Draw the itinerary (it must hold an item), keep the images and return their
        addresses. Raises `ItineraryRenderError` when it cannot be drawn."""
        rendered = await self.renderer.render(itinerary_view_of(itinerary))
        names = [self.store.save(group_id, png) for png in rendered.images]
        urls = [f"{self.public_base_url}{MEDIA_PATH}{name}" for name in names]
        return ItineraryImageSet(urls, rendered.omitted_day_count)

    def create_blocking(self, group_id: str, itinerary: Itinerary) -> ItineraryImageSet | None:
        """Do `create` on a worker thread and wait for it; return None, after a log line, when
        the images could not be made. One drawing runs at a time."""
        future = self._worker.submit(asyncio.run, self.create(group_id, itinerary))
        try:
            return future.result(timeout=DRAW_WAIT_SECONDS)
        except FutureTimeoutError:
            logger.warning("itinerary images: drawing took longer than %ds", DRAW_WAIT_SECONDS)
        except Exception as error:  # nothing in drawing may end the answer; the card replaces it
            logger.warning("itinerary images: could not draw (%s)", error)
        return None
