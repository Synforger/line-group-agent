"""The photos of each group, one file per photo.

Lives at `<state_dir>/groups/<groupId>/images/<message id>.<jpg|png|gif|webp>`. Written by
the media recorder, read when a photo is given to the model, and removed with its message
(on request, when unsent, or when it outlives the retention period).
"""

from __future__ import annotations

import re
from pathlib import Path

from line_group_agent._common.atomic_write import write_bytes_atomically
from line_group_agent.media.image_shrinker import StoredImage
from line_group_agent.records.group_folder import group_folder
from line_group_agent.records.group_log import IMAGES_FOLDER_NAME

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
MEDIA_TYPES = {extension: media_type for media_type, extension in EXTENSIONS.items()}
UNSAFE_NAME_CHARS = re.compile(r"[^A-Za-z0-9_-]")


class ImageStore:
    """Saves and reads the photo files under one state folder."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def save(self, group_id: str, message_id: str, image: StoredImage) -> str:
        """Write the photo of this message and return its file name."""
        name = f"{UNSAFE_NAME_CHARS.sub('_', message_id)}.{EXTENSIONS[image.media_type]}"
        write_bytes_atomically(self._folder(group_id) / name, image.data)
        return name

    def read(self, group_id: str, name: str) -> StoredImage | None:
        """Return the photo with this file name, or None when it is gone or not one of ours."""
        media_type = MEDIA_TYPES.get(Path(name).suffix.lstrip("."))
        if media_type is None:
            return None
        try:
            return StoredImage((self._folder(group_id) / Path(name).name).read_bytes(), media_type)
        except OSError:
            return None

    def _folder(self, group_id: str) -> Path:
        return group_folder(self.state_dir, group_id) / IMAGES_FOLDER_NAME
