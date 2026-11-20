"""A group's trip itinerary as values: the trip (a name, a first day), its items, and how they
read as text.

Plain values kept by the itinerary book in the group's `itinerary.json`; read by the itinerary
tools, the card, the event dispatcher and the LIFF page's view.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

MAX_DAY = 30
MINUTES_PER_HOUR = 60
WEEKDAY_NAMES = "月火水木金土日"
UNTIMED_LABEL = "時間未定"
NO_ITEMS_TEXT = "(予定はまだありません)"


def minutes_of(time: str) -> int:
    """Return the minutes since midnight of a `HH:MM` time."""
    hours, minutes = time.split(":")
    return int(hours) * MINUTES_PER_HOUR + int(minutes)


@dataclass(frozen=True)
class ItineraryItem:
    """One thing on the itinerary. `day` counts from 1 (the first day of the trip); `start` and
    `end` are `HH:MM`, and an item without `start` has no fixed time. `id` is short and
    unguessable: the model names an item by it."""

    id: str
    day: int
    title: str
    start: str | None = None
    end: str | None = None
    place: str | None = None
    note: str | None = None
    url: str | None = None

    def line(self, *, with_id: bool = False) -> str:
        """Return the item on one line: the time, the title, then the place, note and url when
        there are any (`[id]` first with `with_id`, for the model)."""
        if self.start is None:
            time = UNTIMED_LABEL
        else:
            time = f"{self.start}-{self.end}" if self.end else f"{self.start}-"
        parts = [f"[{self.id}]" if with_id else "", time, self.title]
        if self.place:
            parts.append(f"({self.place})")
        if self.note:
            parts.append(f"/ {self.note}")
        if self.url:
            parts.append(self.url)
        return " ".join(part for part in parts if part)


@dataclass(frozen=True)
class Itinerary:
    """The itinerary of a group. `start_date` is the ISO date of day 1 when it is known.
    `legacy_text` is the whole text an earlier version of this program kept in place of items;
    it stays beside the items so nothing the group wrote is lost. `link_id` is the unguessable
    id the page's link carries (empty until the itinerary is first changed or shown)."""

    title: str
    start_date: str | None
    items: tuple[ItineraryItem, ...]
    saved_at: str
    link_id: str = ""
    legacy_text: str = ""

    def date_of_day(self, day: int) -> date | None:
        """Return the calendar date of this day of the trip, or None without a first day."""
        if self.start_date is None:
            return None
        return date.fromisoformat(self.start_date) + timedelta(days=day - 1)

    def day_heading(self, day: int) -> str:
        """Return `11/23(月) 1日目`, or `1日目` when the first day is not known."""
        found = self.date_of_day(day)
        if found is None:
            return f"{day}日目"
        return f"{found.month}/{found.day}({WEEKDAY_NAMES[found.weekday()]}) {day}日目"

    def sorted_items(self) -> list[ItineraryItem]:
        """Return the items by day, items without a time first, then by start and end time.
        Items that tie keep the order they were added in."""
        return sorted(
            self.items,
            key=lambda item: (
                item.day,
                item.start is not None,
                item.start or "",
                item.end or "",
            ),
        )

    @property
    def text(self) -> str:
        """The itinerary as plain text for the members: the title, then each day's heading
        and its items. An itinerary that holds only the earlier text gives that text."""
        if not self.items and self.legacy_text:
            return self.legacy_text
        lines = [self.title] if self.title else []
        current_day = 0
        for item in self.sorted_items():
            if item.day != current_day:
                current_day = item.day
                lines.extend(
                    ["", self.day_heading(current_day)]
                    if lines
                    else [self.day_heading(current_day)]
                )
            lines.append(item.line())
        return "\n".join(lines) if self.items or self.title else NO_ITEMS_TEXT
