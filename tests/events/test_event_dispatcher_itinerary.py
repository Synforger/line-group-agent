"""A mention that is only the itinerary keyword gets the saved itinerary, without the model."""

from datetime import datetime
from pathlib import Path

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher, NoticeTexts
from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import (
    ALLOWED,
    ScriptedAnswerer,
    mention_text_event,
    text_event,
)
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
ITINERARY = "1日目 (11/23)\nKyoto"


def setup(
    tmp_path: Path, *, saved: str | None = ITINERARY, **options: object
) -> tuple[EventDispatcher, FakeLine, GroupLog, ScriptedAnswerer]:
    line = FakeLine(names={"U1": "Aki"})
    group_log = GroupLog(tmp_path)
    answerer = ScriptedAnswerer()
    book = ItineraryBook(tmp_path, lambda: datetime(2026, 11, 18, 12, 0).astimezone())
    if saved is not None:
        book.update(ALLOWED, saved)
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        group_log,
        answerer,
        texts=NoticeTexts(itinerary_keywords=("itinerary", "しおり")),
        itineraries=book,
        **options,  # type: ignore[arg-type]
    )
    return dispatcher, line, group_log, answerer


@pytest.mark.parametrize(
    "text", ["@bot itinerary", "@bot ITINERARY?", "@bot しおり", "@bot  itinerary!"]
)
async def test_the_keyword_gets_the_saved_text_without_the_model(tmp_path: Path, text: str) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    await dispatcher.handle(mention_text_event(text))
    assert answerer.calls == []
    assert line.replies == [("reply-token-1", ITINERARY)]
    assert line.calls[0].quote_token == "quote-m1"
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False]


async def test_a_longer_question_goes_to_the_model(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    await dispatcher.handle(mention_text_event("@bot itinerary for day two?"))
    assert len(answerer.calls) == 1 and line.replies == [("reply-token-1", "Sure.")]


async def test_without_a_saved_itinerary_the_model_answers(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path, saved=None)
    await dispatcher.handle(mention_text_event("@bot itinerary"))
    assert len(answerer.calls) == 1 and line.replies == [("reply-token-1", "Sure.")]


async def test_calling_by_name_with_the_keyword_works_too(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path, call_names=("Sora",))
    await dispatcher.handle(text_event(text="Sora, itinerary"))
    assert answerer.calls == [] and line.replies == [("reply-token-1", ITINERARY)]


async def test_a_plain_message_with_the_keyword_is_not_a_call(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    await dispatcher.handle(text_event(text="itinerary"))
    assert answerer.calls == [] and line.calls == []
