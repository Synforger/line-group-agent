"""The trip itinerary of each group, kept as one item per entry.

Lives at `<state_dir>/groups/<groupId>/itinerary.json`, replaced whole at each change:
`{"title", "start_date", "items", "link_id", "legacy_text", "saved_at", "versions"}`. Every
change keeps the state it replaces, the last `MAX_VERSIONS_KEPT` of them, so a wrong change can
be put back. A file in the earlier shape (one `text`) is read as an itinerary with no items
and that text as `legacy_text`. Called by the itinerary tools, the LIFF page and the event
dispatcher.
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent.itinerary.item_input import (
    NOTE_MAX_CHARS,
    PLACE_MAX_CHARS,
    TITLE_MAX_CHARS,
    TRIP_TITLE_MAX_CHARS,
    ItemInputError,
    day_of,
    start_date_of,
    text_of,
    time_of,
    url_of,
)
from line_group_agent.itinerary.itinerary import Itinerary, ItineraryItem
from line_group_agent.records.group_folder import group_folder
from line_group_agent.records.group_log import GROUP_ID_PATTERN
from line_group_agent.records.json_document import read_json_document, write_json_document

ITINERARY_FILE_NAME = "itinerary.json"
MAX_VERSIONS_KEPT = 5
MAX_ITEM_COUNT = 150
ITEM_ID_BYTES = 3
# 16 random bytes in base64url: 128 bits, 22 characters.
LINK_ID_BYTES = 16
LINK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
ITEM_FIELD_NAMES = ("day", "title", "start", "end", "place", "note", "url")
NO_ITINERARY = Itinerary("", None, (), "")


@dataclass(frozen=True)
class ItineraryLocation:
    """An itinerary and the group it belongs to, found by the id of its page's link."""

    group_id: str
    itinerary: Itinerary


class ItineraryBook:
    """Reads and changes the itineraries under one state folder."""

    def __init__(self, state_dir: Path, clock: Callable[[], datetime]) -> None:
        self.state_dir = state_dir
        self._clock = clock

    def get(self, group_id: str) -> Itinerary | None:
        """Return the group's current itinerary, or None when none was saved."""
        return _itinerary_of(self._read(group_id))

    def versions(self, group_id: str) -> list[Itinerary]:
        """Return the states that were replaced, newest first (at most five)."""
        return _versions_of(self._read(group_id))

    def link_id(self, group_id: str) -> str | None:
        """Return the id the page's link of this group's itinerary carries, making and keeping
        one when the itinerary has none yet. None when the group has no itinerary."""
        current = self.get(group_id)
        if current is None:
            return None
        if current.link_id:
            return current.link_id
        made = replace(current, link_id=_new_link_id())
        self._write(group_id, made, self.versions(group_id))
        return made.link_id

    def find_by_link_id(self, link_id: str) -> ItineraryLocation | None:
        """Return the itinerary whose page's link carries this id, with its group, or None when
        no group has one (an id of the wrong shape is not looked up at all)."""
        if not LINK_ID_PATTERN.match(link_id):
            return None
        try:
            folders = sorted((self.state_dir / "groups").iterdir())
        except OSError:
            return None
        for folder in folders:
            if not GROUP_ID_PATTERN.match(folder.name):
                continue
            found = self.get(folder.name)
            if (
                found
                and found.link_id
                and secrets.compare_digest(found.link_id.encode(), link_id.encode())
            ):
                return ItineraryLocation(folder.name, found)
        return None

    def add_item(
        self,
        group_id: str,
        *,
        day: int,
        title: str,
        start: str | None = None,
        end: str | None = None,
        place: str | None = None,
        note: str | None = None,
        url: str | None = None,
    ) -> ItineraryItem:
        """Add an item (the caller has checked its fields and that there is room) and return it
        with its new id."""
        current = self.get(group_id) or NO_ITINERARY
        taken = {item.id for item in current.items}
        item_id = secrets.token_hex(ITEM_ID_BYTES)
        while item_id in taken:
            item_id = secrets.token_hex(ITEM_ID_BYTES)
        item = ItineraryItem(item_id, day, title, start, end, place, note, url)
        self._change(group_id, replace(current, items=(*current.items, item)))
        return item

    def change_item(
        self, group_id: str, item_id: str, changes: Mapping[str, object]
    ) -> ItineraryItem | None:
        """Change the fields named in `changes` (`day`, `title`, `start`, `end`, `place`, `note`,
        `url`; None clears an optional one) and return the item, or None when no item has this
        id. Nothing is written when no field differs."""
        current = self.get(group_id)
        found = (
            next((item for item in current.items if item.id == item_id), None) if current else None
        )
        if current is None or found is None:
            return None
        changed = replace(
            found, **{name: value for name, value in changes.items() if name in ITEM_FIELD_NAMES}
        )
        if changed != found:
            items = tuple(changed if item.id == item_id else item for item in current.items)
            self._change(group_id, replace(current, items=items))
        return changed

    def remove_item(self, group_id: str, item_id: str) -> ItineraryItem | None:
        """Remove the item and return it, or None when no item has this id."""
        current = self.get(group_id)
        found = (
            next((item for item in current.items if item.id == item_id), None) if current else None
        )
        if current is None or found is None:
            return None
        self._change(
            group_id, replace(current, items=tuple(i for i in current.items if i != found))
        )
        return found

    def change_trip(self, group_id: str, changes: Mapping[str, str | None]) -> bool:
        """Set the trip's `title` and/or `start_date` (None clears it), making the itinerary
        when there is none. Return False, writing nothing, when neither differs."""
        current = self.get(group_id) or NO_ITINERARY
        changed = replace(
            current,
            title=(changes["title"] or "") if "title" in changes else current.title,
            start_date=changes["start_date"] if "start_date" in changes else current.start_date,
        )
        if changed == current:
            return False
        self._change(group_id, changed)
        return True

    def restore(self, group_id: str, version: int = 1) -> Itinerary | None:
        """Put back an earlier state (1 is the newest of those `versions` lists) as the
        current one, keeping the state it replaces. None when there is no such version."""
        current = self.get(group_id)
        earlier = self.versions(group_id)
        if current is None or not 1 <= version <= len(earlier):
            return None
        chosen = replace(earlier[version - 1], link_id=current.link_id)
        self._change(group_id, chosen)
        return self.get(group_id)

    def _change(self, group_id: str, after: Itinerary) -> None:
        """Write `after` as the current state and keep the one it replaces."""
        before = self.get(group_id)
        kept = self.versions(group_id)
        if before is not None:
            kept = [before, *kept][:MAX_VERSIONS_KEPT]
        self._write(
            group_id, replace(after, saved_at=self._clock().isoformat(timespec="seconds")), kept
        )

    def _write(self, group_id: str, itinerary: Itinerary, kept: list[Itinerary]) -> None:
        document = _snapshot_row(itinerary)
        document["link_id"] = itinerary.link_id or _new_link_id()
        document["versions"] = [_snapshot_row(version) for version in kept]
        write_json_document(self._path(group_id), document)

    def _read(self, group_id: str) -> dict[str, Any]:
        return read_json_document(self._path(group_id))

    def _path(self, group_id: str) -> Path:
        return group_folder(self.state_dir, group_id) / ITINERARY_FILE_NAME


def _new_link_id() -> str:
    return secrets.token_urlsafe(LINK_ID_BYTES)


def _versions_of(document: dict[str, Any]) -> list[Itinerary]:
    rows = document.get("versions")
    if not isinstance(rows, list):
        return []
    return [found for row in rows if (found := _itinerary_of(row)) is not None]


def _itinerary_of(row: Any) -> Itinerary | None:
    """Read one state: the current document or one of its versions. A row of the earlier
    shape (a `text`) has no items and keeps its text as `legacy_text`."""
    if not isinstance(row, dict):
        return None
    items = tuple(
        item for raw in _list_of(row.get("items")) if (item := _item_of(raw)) is not None
    )[:MAX_ITEM_COUNT]
    legacy = row.get("legacy_text", row.get("text"))
    itinerary = Itinerary(
        title=_clean(row.get("title"), TRIP_TITLE_MAX_CHARS) or "",
        start_date=_start_date_of(row.get("start_date")),
        items=items,
        saved_at=str(row.get("saved_at", "")),
        link_id=row["link_id"] if _is_link_id(row.get("link_id")) else "",
        legacy_text=legacy if isinstance(legacy, str) else "",
    )
    if not (itinerary.items or itinerary.title or itinerary.start_date or itinerary.legacy_text):
        return None
    return itinerary


def _item_of(row: Any) -> ItineraryItem | None:
    if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
        return None
    try:
        return ItineraryItem(
            id=row["id"],
            day=day_of(row.get("day")),
            title=text_of(row.get("title"), "title", TITLE_MAX_CHARS, is_required=True) or "",
            start=time_of(row.get("start"), "start"),
            end=time_of(row.get("end"), "end") if row.get("start") else None,
            place=text_of(row.get("place"), "place", PLACE_MAX_CHARS),
            note=text_of(row.get("note"), "note", NOTE_MAX_CHARS),
            url=url_of(row.get("url")),
        )
    except ItemInputError:
        return None


def _snapshot_row(itinerary: Itinerary) -> dict[str, Any]:
    row: dict[str, Any] = {"title": itinerary.title}
    if itinerary.start_date:
        row["start_date"] = itinerary.start_date
    row["items"] = [
        {"id": item.id, "day": item.day, "title": item.title}
        | {
            name: value
            for name in ("start", "end", "place", "note", "url")
            if (value := getattr(item, name))
        }
        for item in itinerary.items
    ]
    if itinerary.legacy_text:
        row["legacy_text"] = itinerary.legacy_text
    row["saved_at"] = itinerary.saved_at
    return row


def _list_of(raw: Any) -> list[Any]:
    return raw if isinstance(raw, list) else []


def _clean(raw: object, limit: int) -> str | None:
    try:
        return text_of(raw, "title", limit)
    except ItemInputError:
        return None


def _start_date_of(raw: object) -> str | None:
    try:
        return start_date_of(raw)
    except ItemInputError:
        return None


def _is_link_id(raw: object) -> bool:
    return isinstance(raw, str) and LINK_ID_PATTERN.match(raw) is not None
