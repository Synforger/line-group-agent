from datetime import datetime, timedelta, timezone

from line_group_agent.itinerary.itinerary import Itinerary, ItineraryItem
from line_group_agent.itinerary.itinerary_message import (
    build_itinerary_message,
    itinerary_record_line,
    liff_itinerary_url,
)
from line_group_agent.itinerary.itinerary_upcoming import upcoming_items

TOKYO = timezone(timedelta(hours=9))
LIFF_ID = "1234567890-AbCdEfGh"
LINK_ID = "L" * 22


def item(item_id: str, day: int, title: str, start: str | None = None, end: str | None = None):
    return ItineraryItem(item_id, day, title, start, end)


def plan(
    *items: ItineraryItem, start_date: str | None = "2026-11-23", title: str = ""
) -> Itinerary:
    return Itinerary(title, start_date, items, "", LINK_ID)


def at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=TOKYO)


FIVE = plan(
    item("a", 1, "Breakfast", "08:00", "09:00"),
    item("b", 1, "Kiyomizu", "10:00", "12:00"),
    item("c", 1, "Dinner", "18:00"),
    item("d", 2, "Arashiyama", "09:00"),
    item("e", 2, "Souvenirs"),
)


def titles(items: list[ItineraryItem]) -> list[str]:
    return [found.title for found in items]


def test_before_the_trip_the_first_three_are_next() -> None:
    assert titles(upcoming_items(FIVE, at(20, 12))) == ["Breakfast", "Kiyomizu", "Dinner"]


def test_an_item_is_over_when_its_end_has_passed() -> None:
    assert titles(upcoming_items(FIVE, at(23, 9, 0))) == ["Kiyomizu", "Dinner", "Souvenirs"]
    assert titles(upcoming_items(FIVE, at(23, 8, 59)))[0] == "Breakfast"
    assert titles(upcoming_items(FIVE, at(23, 11, 59)))[0] == "Kiyomizu"
    assert titles(upcoming_items(FIVE, at(23, 12, 0)))[0] == "Dinner"


def test_an_item_without_an_end_lasts_an_hour_and_one_without_a_time_lasts_the_day() -> None:
    assert titles(upcoming_items(FIVE, at(23, 18, 59)))[0] == "Dinner"
    assert titles(upcoming_items(FIVE, at(23, 19, 0)))[0] == "Souvenirs"
    assert titles(upcoming_items(FIVE, at(24, 8, 0)))[0] == "Souvenirs"


def test_on_the_last_day_the_untimed_item_stays_until_the_day_ends() -> None:
    assert titles(upcoming_items(FIVE, at(24, 23, 30))) == ["Souvenirs"]


def test_when_the_trip_is_over_the_last_three_are_shown() -> None:
    assert titles(upcoming_items(FIVE, at(30, 12))) == ["Dinner", "Souvenirs", "Arashiyama"]


def test_without_a_first_day_the_first_three_are_next() -> None:
    assert titles(upcoming_items(plan(*FIVE.items, start_date=None), at(30, 12))) == [
        "Breakfast",
        "Kiyomizu",
        "Dinner",
    ]


def test_the_card_has_the_next_three_and_one_button_to_the_page() -> None:
    message = build_itinerary_message(plan(*FIVE.items, title="Kyoto"), LIFF_ID, at(23, 9))
    body = message["contents"]["body"]["contents"]
    assert body[0]["text"] == "Kyoto"
    rows = [row["contents"][1]["text"] for row in body[1:-1]]
    assert rows == ["Kiyomizu", "Dinner", "Souvenirs"]
    assert body[1]["contents"][0]["text"] == "11/23 10:00"
    assert body[3]["contents"][0]["text"] == "11/24 時間未定"
    button = body[-1]
    assert button["action"]["label"] == "予定表を開く"
    assert button["action"]["uri"] == f"https://liff.line.me/{LIFF_ID}/itinerary?i={LINK_ID}"
    assert message["altText"].startswith("Kyoto / Kiyomizu")


def test_a_card_without_a_first_day_names_the_day_by_its_number() -> None:
    message = build_itinerary_message(plan(*FIVE.items, start_date=None), LIFF_ID, at(23, 9))
    assert message["contents"]["body"]["contents"][0]["text"] == "旅の予定表"
    assert message["contents"]["body"]["contents"][1]["contents"][0]["text"] == "1日目 08:00"


def test_the_url_and_the_record_line() -> None:
    assert liff_itinerary_url(LIFF_ID, LINK_ID).endswith(f"/itinerary?i={LINK_ID}")
    assert itinerary_record_line(plan(*FIVE.items, title="Kyoto")) == "[予定表] Kyoto (5件)"
