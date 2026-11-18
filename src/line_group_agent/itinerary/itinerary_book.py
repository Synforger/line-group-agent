"""The trip itinerary of each group: one plain text the whole group edits through the bot.

Lives at `<state_dir>/groups/<groupId>/itinerary.json`, replaced whole at each change. An
update replaces the whole text and keeps the version it replaced, the last
`MAX_VERSIONS_KEPT` of them, so a wrong update can be put back by hand.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent.records.group_folder import group_folder
from line_group_agent.records.json_document import read_json_document, write_json_document

ITINERARY_FILE_NAME = "itinerary.json"
MAX_VERSIONS_KEPT = 5


@dataclass(frozen=True)
class Itinerary:
    """The text of an itinerary and when it was saved (ISO 8601)."""

    text: str
    saved_at: str


class ItineraryBook:
    """Reads and replaces the itineraries under one state folder."""

    def __init__(self, state_dir: Path, clock: Callable[[], datetime]) -> None:
        self.state_dir = state_dir
        self._clock = clock

    def get(self, group_id: str) -> Itinerary | None:
        """Return the group's current itinerary, or None when none was saved."""
        return _itinerary_of(self._read(group_id))

    def versions(self, group_id: str) -> list[Itinerary]:
        """Return the versions that were replaced, newest first (at most five)."""
        rows = self._read(group_id).get("versions")
        if not isinstance(rows, list):
            return []
        return [found for row in rows if (found := _itinerary_of(row)) is not None]

    def update(self, group_id: str, text: str) -> bool:
        """Replace the whole itinerary by `text`, keeping the one it replaces. Return False
        (and write nothing) when `text` is what is already saved."""
        current = self.get(group_id)
        if current is not None and current.text == text:
            return False
        kept = self.versions(group_id)
        if current is not None:
            kept = [current, *kept][:MAX_VERSIONS_KEPT]
        document = {
            "text": text,
            "saved_at": self._clock().isoformat(timespec="seconds"),
            "versions": [_row_of(version) for version in kept],
        }
        write_json_document(self._path(group_id), document)
        return True

    def _read(self, group_id: str) -> dict[str, Any]:
        return read_json_document(self._path(group_id))

    def _path(self, group_id: str) -> Path:
        return group_folder(self.state_dir, group_id) / ITINERARY_FILE_NAME


def _itinerary_of(row: Any) -> Itinerary | None:
    if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"]:
        return None
    return Itinerary(row["text"], str(row.get("saved_at", "")))


def _row_of(itinerary: Itinerary) -> dict[str, str]:
    return {"text": itinerary.text, "saved_at": itinerary.saved_at}
