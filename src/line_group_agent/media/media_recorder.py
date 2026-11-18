"""Take in the photos members send: read the photo from LINE, make it small enough for the
model, keep it, and give the name of its file for the group's record.

The record holds a line `[写真]` for the photo, and its file name beside it. LINE keeps the
content of a message only for a while, so it is read at once when the message arrives.
Called by the event dispatcher.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from line_group_agent.media.image_shrinker import shrink_image
from line_group_agent.media.image_store import ImageStore

logger = logging.getLogger(__name__)

IMAGE_RECORD_TEXT = "[写真]"


class ContentSource(Protocol):
    """What the recorder needs from the LINE client: the bytes of a member's image."""

    async def get_message_content(self, message_id: str) -> tuple[bytes, str] | None: ...


class MediaRecorder:
    """Reads, shrinks and keeps the photos of the group."""

    def __init__(self, line: ContentSource, store: ImageStore, max_edge_pixels: int) -> None:
        self.line = line
        self.store = store
        self.max_edge_pixels = max_edge_pixels

    async def save_image(self, group_id: str, message_id: str) -> str | None:
        """Keep the photo of this message and return its file name, or None when LINE did not
        give it or it is not an image the model can be given."""
        fetched = await self.line.get_message_content(message_id)
        if fetched is None:
            logger.info("image: LINE did not give the content of a photo")
            return None
        image = await asyncio.to_thread(shrink_image, fetched[0], self.max_edge_pixels)
        if image is None:
            logger.info("image: a photo could not be used")
            return None
        try:
            return self.store.save(group_id, message_id, image)
        except OSError as error:
            logger.warning("image: a photo could not be saved (%s)", type(error).__name__)
            return None
