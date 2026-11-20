"""The itinerary images kept for LINE to fetch, one PNG file each.

Lives at `<state_dir>/groups/<groupId>/itinerary-images/<id>.png`, where the id is 128
random bits, so the file's address cannot be guessed. Written when the bot draws the plan,
read by the LIFF router that serves `/liff/media/<id>.png`, and removed after
`IMAGE_KEEP_DAYS`.
"""

from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path

from line_group_agent._common.atomic_write import write_bytes_atomically
from line_group_agent.records.group_folder import group_folder

IMAGE_FOLDER_NAME = "itinerary-images"
IMAGE_SUFFIX = ".png"
IMAGE_ID_BYTES = 16
IMAGE_KEEP_DAYS = 30
IMAGE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}\.png$")

logger = logging.getLogger(__name__)


class ItineraryImageStore:
    """Saves, reads and expires the itinerary images under one state folder."""

    def __init__(self, state_dir: Path, clock: Callable[[], datetime]) -> None:
        self.state_dir = state_dir
        self._clock = clock

    def save(self, group_id: str, png: bytes) -> str:
        """Write an image into the group's folder and return its file name. Images past
        their keeping time are removed first."""
        self.remove_expired()
        name = secrets.token_urlsafe(IMAGE_ID_BYTES) + IMAGE_SUFFIX
        folder = group_folder(self.state_dir, group_id) / IMAGE_FOLDER_NAME
        write_bytes_atomically(folder / name, png)
        return name

    def read(self, name: str) -> bytes | None:
        """Return the image with this file name, or None when it is gone, expired or not a
        name this store made."""
        if not IMAGE_NAME_PATTERN.match(name):
            return None
        for file in self._files_named(name):
            if self._is_expired(file):
                continue
            try:
                return file.read_bytes()
            except OSError:
                return None
        return None

    def remove_expired(self) -> int:
        """Delete the images of every group that are older than the keeping time and return
        how many were deleted."""
        removed = 0
        for file in self._files_named("*" + IMAGE_SUFFIX):
            if not self._is_expired(file):
                continue
            try:
                file.unlink()
            except OSError:
                logger.warning("itinerary images: could not delete an expired image")
                continue
            removed += 1
        return removed

    def _files_named(self, pattern: str) -> list[Path]:
        return sorted((self.state_dir / "groups").glob(f"*/{IMAGE_FOLDER_NAME}/{pattern}"))

    def _is_expired(self, file: Path) -> bool:
        try:
            saved_at = datetime.fromtimestamp(file.stat().st_mtime, tz=self._clock().tzinfo)
        except OSError:
            return True
        return self._clock() - saved_at > timedelta(days=IMAGE_KEEP_DAYS)
