"""A mention that is only the itinerary keyword gets the saved itinerary, without the model."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher, NoticeTexts
from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.itinerary.itinerary_replier import EMPTY_TEXT, MEMO_TEXT, ItineraryReplier
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import (
    ALLOWED,
    ScriptedAnswerer,
    mention_text_event,
    text_event,
)
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
LIFF_ID = "1234567890-AbCdEfGh"
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=timezone(timedelta(hours=9)))
LEGACY_TEXT = "1日目 (11/23)\nKyoto"


def setup(
    tmp_path: Path,
    *,
    items: tuple[str, ...] = ("Kiyomizu",),
    liff_id: str | None = LIFF_ID,
    **options: object,
) -> tuple[EventDispatcher, FakeLine, GroupLog, ScriptedAnswerer, ItineraryBook]:
    line = FakeLine(names={"U1": "Aki"})
    group_log = GroupLog(tmp_path)
    answerer = ScriptedAnswerer()
    book = ItineraryBook(tmp_path, lambda: NOW)
    for title in items:
        book.add_item(ALLOWED, day=1, title=title, start="09:00")
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        group_log,
        answerer,
        texts=NoticeTexts(itinerary_keywords=("itinerary", "しおり")),
        itineraries=ItineraryReplier(book, liff_id=liff_id, clock=lambda: NOW),
        **options,  # type: ignore[arg-type]
    )
    return dispatcher, line, group_log, answerer, book


def write_memo_only(tmp_path: Path) -> None:
    folder = tmp_path / "groups" / ALLOWED
    folder.mkdir(parents=True)
    (folder / "itinerary.json").write_text(
        json.dumps({"text": LEGACY_TEXT, "saved_at": "2026-11-17T09:00:00+09:00"})
    )


@pytest.mark.parametrize(
    "text", ["@bot itinerary", "@bot ITINERARY?", "@bot しおり", "@bot  itinerary!"]
)
async def test_the_keyword_gets_the_card_without_the_model(tmp_path: Path, text: str) -> None:
    dispatcher, line, group_log, answerer, book = setup(tmp_path)
    await dispatcher.handle(mention_text_event(text))
    assert answerer.calls == []
    assert len(line.calls) == 1 and line.calls[0].text is None
    assert line.calls[0].quote_token == "quote-m1"
    (extra,) = line.calls[0].extras
    assert extra.message["type"] == "flex"
    assert f"{LIFF_ID}/itinerary?i={book.link_id(ALLOWED)}" in str(extra.message)
    assert "Kiyomizu" in str(extra.message)
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False]


async def test_the_card_shows_only_the_next_three(tmp_path: Path) -> None:
    dispatcher, line, _, _, _ = setup(tmp_path, items=("A", "B", "C", "D", "E"))
    await dispatcher.handle(mention_text_event("@bot itinerary"))
    (extra,) = line.calls[0].extras
    shown = [
        row["contents"][1]["text"] for row in extra.message["contents"]["body"]["contents"][1:-1]
    ]
    assert shown == ["A", "B", "C"]


async def test_without_a_page_the_itinerary_is_sent_as_text(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, _ = setup(tmp_path, liff_id=None)
    await dispatcher.handle(mention_text_event("@bot itinerary"))
    assert answerer.calls == []
    assert line.replies == [("reply-token-1", "1日目\n09:00- Kiyomizu")]
    assert line.calls[0].extras == []


async def test_an_itinerary_with_nothing_in_it_gets_one_short_line(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, book = setup(tmp_path, items=())
    book.change_trip(ALLOWED, {"title": "Kyoto trip"})
    await dispatcher.handle(mention_text_event("@bot itinerary"))
    assert answerer.calls == []
    assert line.replies == [("reply-token-1", EMPTY_TEXT)] and line.calls[0].extras == []


async def test_an_earlier_memo_alone_is_said_and_the_button_opens_the_page(tmp_path: Path) -> None:
    write_memo_only(tmp_path)
    dispatcher, line, _, answerer, book = setup(tmp_path, items=())
    await dispatcher.handle(mention_text_event("@bot itinerary"))
    assert answerer.calls == []
    assert line.replies == [("reply-token-1", MEMO_TEXT)]
    (extra,) = line.calls[0].extras
    assert f"/itinerary?i={book.link_id(ALLOWED)}" in str(extra.message)


async def test_a_longer_question_goes_to_the_model(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, _ = setup(tmp_path)
    await dispatcher.handle(mention_text_event("@bot itinerary for day two?"))
    assert len(answerer.calls) == 1 and line.replies == [("reply-token-1", "Sure.")]


async def test_without_a_saved_itinerary_the_model_answers(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, _ = setup(tmp_path, items=())
    await dispatcher.handle(mention_text_event("@bot itinerary"))
    assert len(answerer.calls) == 1 and line.replies == [("reply-token-1", "Sure.")]


async def test_calling_by_name_with_the_keyword_works_too(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, _ = setup(tmp_path, call_names=("Sora",))
    await dispatcher.handle(text_event(text="Sora, itinerary"))
    assert answerer.calls == [] and len(line.calls[0].extras) == 1


async def test_a_plain_message_with_the_keyword_is_not_a_call(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, _ = setup(tmp_path)
    await dispatcher.handle(text_event(text="itinerary"))
    assert answerer.calls == [] and line.calls == []
