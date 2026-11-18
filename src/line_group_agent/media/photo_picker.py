"""Choose the photos to show the model at a mention: those the group sent since the bot's
last turn, the newest few, read from the image store.

Called by the answerer when it builds the user turn.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from line_group_agent.media.image_store import ImageStore
from line_group_agent.records.group_log import GroupMessage


@dataclass(frozen=True)
class Photo:
    """A photo ready for the request: the message it came with, its type and its base64 bytes."""

    message: GroupMessage
    media_type: str
    data: str


class PhotoPicker:
    """Reads the photos that go with a turn."""

    def __init__(self, store: ImageStore, max_images_per_turn: int) -> None:
        self.store = store
        self.max_images_per_turn = max_images_per_turn

    def pick(self, group_id: str, messages: list[GroupMessage]) -> list[Photo]:
        """Return the photos of the newest `max_images_per_turn` photo messages among
        `messages` (oldest first); a photo whose file is gone is left out."""
        if self.max_images_per_turn <= 0:
            return []
        with_photos = [m for m in messages if m.image_file and not m.from_bot]
        photos: list[Photo] = []
        for message in with_photos[-self.max_images_per_turn :]:
            image = self.store.read(group_id, message.image_file or "")
            if image is not None:
                photos.append(
                    Photo(message, image.media_type, base64.b64encode(image.data).decode("ascii"))
                )
        return photos
