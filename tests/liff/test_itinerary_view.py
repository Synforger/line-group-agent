from line_group_agent.itinerary.itinerary import Itinerary, ItineraryItem
from line_group_agent.liff.itinerary_view import itinerary_view_of, map_url_of


def item(item_id: str, day: int, title: str, **fields: str) -> ItineraryItem:
    return ItineraryItem(item_id, day, title, **fields)  # type: ignore[arg-type]


def test_the_view_has_a_day_for_each_day_up_to_the_last_one_with_an_item() -> None:
    plan = Itinerary("Kyoto", "2026-11-23", (item("a", 3, "Last"),), "")
    view = itinerary_view_of(plan)
    assert [(d["day"], d["label"], d["date"]) for d in view["days"]] == [
        (1, "11/23(月) 1日目", "2026-11-23"),
        (2, "11/24(火) 2日目", "2026-11-24"),
        (3, "11/25(水) 3日目", "2026-11-25"),
    ]
    assert view["days"][0]["scheduled"] == [] and view["days"][0]["axis"] is None
    assert view["title"] == "Kyoto" and view["start_date"] == "2026-11-23"


def test_without_a_first_day_the_days_have_no_dates() -> None:
    view = itinerary_view_of(Itinerary("", None, (item("a", 2, "x"),), ""))
    assert [(d["label"], d["date"]) for d in view["days"]] == [("1日目", None), ("2日目", None)]


def test_an_itinerary_with_no_items_has_no_days_and_keeps_its_memo() -> None:
    view = itinerary_view_of(Itinerary("", None, (), "", legacy_text="1日目\nKyoto"))
    assert view["days"] == [] and view["legacy_text"] == "1日目\nKyoto"


def test_a_day_splits_items_without_a_time_from_the_timed_ones_on_the_axis() -> None:
    plan = Itinerary(
        "",
        None,
        (
            item("a", 1, "Kiyomizu", start="09:00", end="10:30", place="京都 清水寺"),
            item("b", 1, "Free"),
            item("c", 1, "Lunch", start="10:00"),
        ),
        "",
    )
    day = itinerary_view_of(plan)["days"][0]
    assert [i["title"] for i in day["unscheduled"]] == ["Free"]
    assert [i["title"] for i in day["scheduled"]] == ["Kiyomizu", "Lunch"]
    first = day["scheduled"][0]
    assert (first["start_min"], first["end_min"], first["bottom_min"]) == (540, 630, 630)
    assert (first["column"], first["columns"]) == (0, 2)
    assert day["scheduled"][1]["column"] == 1
    assert day["axis"] == {"start_min": 480, "end_min": 720}


def test_a_place_links_to_a_map_search_and_the_text_is_escaped_in_the_address() -> None:
    assert map_url_of("京都 清水寺&x=1") == (
        "https://www.google.com/maps/search/?api=1&query="
        "%E4%BA%AC%E9%83%BD%20%E6%B8%85%E6%B0%B4%E5%AF%BA%26x%3D1"
    )
    plan = Itinerary("", None, (item("a", 1, "x", place="Kyoto"),), "")
    shown = itinerary_view_of(plan)["days"][0]["unscheduled"][0]
    assert shown["map_url"] == map_url_of("Kyoto")
    nothing = itinerary_view_of(Itinerary("", None, (item("a", 1, "x"),), ""))
    assert nothing["days"][0]["unscheduled"][0]["map_url"] is None


def test_only_a_web_address_is_given_as_a_link() -> None:
    plan = Itinerary(
        "",
        None,
        (
            item("a", 1, "x", url="https://example.com"),
            item("b", 1, "y", url="javascript:alert(1)"),
        ),
        "",
    )
    shown = itinerary_view_of(plan)["days"][0]["unscheduled"]
    assert [i["url"] for i in shown] == ["https://example.com", None]


def test_no_item_id_leaves_in_the_view() -> None:
    plan = Itinerary("", None, (item("secret-id", 1, "x", start="09:00"),), "", "L" * 22)
    assert "secret-id" not in str(itinerary_view_of(plan)) and "L" * 22 not in str(
        itinerary_view_of(plan)
    )
