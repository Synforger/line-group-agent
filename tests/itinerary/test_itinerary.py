from line_group_agent.itinerary.itinerary import NO_ITEMS_TEXT, Itinerary, ItineraryItem


def item(item_id: str, day: int, title: str, **fields: str) -> ItineraryItem:
    return ItineraryItem(item_id, day, title, **fields)  # type: ignore[arg-type]


def itinerary(
    *items: ItineraryItem, start_date: str | None = "2026-11-23", **fields: str
) -> Itinerary:
    return Itinerary(
        fields.get("title", ""), start_date, items, "", legacy_text=fields.get("legacy_text", "")
    )


def test_a_day_is_headed_with_its_date_and_weekday_when_the_first_day_is_known() -> None:
    plan = itinerary()
    assert plan.day_heading(1) == "11/23(月) 1日目"
    assert plan.day_heading(8) == "11/30(月) 8日目"
    assert plan.date_of_day(3).isoformat() == "2026-11-25"  # type: ignore[union-attr]


def test_a_day_across_a_month_and_a_year_keeps_counting() -> None:
    plan = itinerary(start_date="2026-12-30")
    assert plan.day_heading(3) == "1/1(金) 3日目"


def test_a_day_is_headed_by_its_number_without_a_first_day() -> None:
    plan = itinerary(start_date=None)
    assert plan.day_heading(2) == "2日目" and plan.date_of_day(2) is None


def test_items_are_sorted_by_day_then_untimed_first_then_start_and_end() -> None:
    late = item("a", 1, "late", start="15:00")
    early_long = item("b", 1, "early long", start="09:00", end="12:00")
    early_short = item("c", 1, "early short", start="09:00", end="10:00")
    untimed = item("d", 1, "untimed")
    second_day = item("e", 2, "second day", start="08:00")
    plan = itinerary(second_day, late, early_long, untimed, early_short)
    assert [i.id for i in plan.sorted_items()] == ["d", "c", "b", "a", "e"]


def test_the_text_lists_each_day_under_its_heading() -> None:
    plan = itinerary(
        item("a", 1, "Kiyomizu", start="09:00", end="10:30", place="Kyoto", note="early"),
        item("b", 1, "Lunch", start="12:00"),
        item("c", 2, "Free day"),
        title="Kyoto trip",
    )
    assert plan.text == (
        "Kyoto trip\n"
        "\n"
        "11/23(月) 1日目\n"
        "09:00-10:30 Kiyomizu (Kyoto) / early\n"
        "12:00- Lunch\n"
        "\n"
        "11/24(火) 2日目\n"
        "時間未定 Free day"
    )


def test_the_text_of_an_itinerary_without_a_title_starts_with_the_first_day() -> None:
    assert itinerary(item("a", 1, "A", start="09:00")).text == "11/23(月) 1日目\n09:00- A"


def test_the_text_of_an_itinerary_of_the_earlier_shape_is_its_memo() -> None:
    assert itinerary(legacy_text="1日目\nKyoto").text == "1日目\nKyoto"


def test_an_itinerary_with_nothing_in_it_still_says_something() -> None:
    assert itinerary().text == NO_ITEMS_TEXT
    assert itinerary(title="Trip").text == "Trip"


def test_the_line_of_an_item_for_the_model_starts_with_its_id() -> None:
    line = item("ab12cd", 1, "Dinner", start="19:00", url="https://example.com").line(with_id=True)
    assert line == "[ab12cd] 19:00- Dinner https://example.com"
