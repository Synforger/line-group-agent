"""What a mention of only the itinerary keyword is answered with, without the model: the
itinerary's card (the next three items and a button to the page).

Without a page (no LIFF app configured) the itinerary is sent as text. An itinerary with no
items gets one short line, and a button when it holds an earlier memo, which the page shows.
Called by the event dispatcher.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime

from line_group_agent.agent.answerer import Answer
from line_group_agent.itinerary.itinerary import Itinerary
from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.itinerary.itinerary_message import (
    build_itinerary_message,
    itinerary_record_line,
)
from line_group_agent.line_api.outgoing_extra import OutgoingExtra

EMPTY_TEXT = "予定表にはまだ予定がありません。"
MEMO_TEXT = "前のメモがあります。予定表のページで見られます。"


class ItineraryReplier:
    """Makes the answer to the itinerary keyword from a group's saved itinerary."""

    def __init__(
        self, book: ItineraryBook, *, liff_id: str | None, clock: Callable[[], datetime]
    ) -> None:
        self.book = book
        self.liff_id = liff_id
        self._clock = clock

    def answer_for(self, group_id: str) -> Answer | None:
        """Return the answer for this group, or None when it has no itinerary (the model
        answers then). It is not recorded as a turn."""
        itinerary = self.book.get(group_id)
        if itinerary is None:
            return None
        if self.liff_id is None:
            return Answer(itinerary.text, record=False)
        if not itinerary.items and not itinerary.legacy_text:
            return Answer(EMPTY_TEXT, record=False)
        card = self._card_of(group_id, itinerary, self.liff_id)
        text = None if itinerary.items else MEMO_TEXT
        return Answer(text, extras=[card], record=False)

    def _card_of(self, group_id: str, itinerary: Itinerary, liff_id: str) -> OutgoingExtra:
        shown = replace(itinerary, link_id=self.book.link_id(group_id) or "")
        return OutgoingExtra(
            build_itinerary_message(shown, liff_id, self._clock()), itinerary_record_line(shown)
        )
