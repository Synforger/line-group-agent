import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.itinerary.itinerary_book import MAX_ITEM_COUNT, ItineraryBook
from line_group_agent.itinerary.itinerary_tools import NO_ITINERARY_RESULT, itinerary_tools
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.records.group_log import GroupMessage

GROUP = "Cgroup"
LIFF_ID = "1234567890-AbCdEfGh"
MENTION = GroupMessage("t", "1", "U1", "Aki", "@bot plan")
TOKYO = timezone(timedelta(hours=9))
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=TOKYO)


class Setup:
    def __init__(self, tmp_path: Path, liff_id: str | None = LIFF_ID) -> None:
        self.book = ItineraryBook(tmp_path, lambda: NOW)
        self.tools = {
            tool.name: tool
            for tool in itinerary_tools(self.book, liff_id=liff_id, clock=lambda: NOW)
        }
        self.output = TurnOutput()

    def run(self, name: str, tool_input: object) -> ToolOutcome:
        tool: ClientTool = self.tools[name]
        return tool.run(tool_input, ToolTurn(GROUP, MENTION, self.output))

    def add(self, day: int, title: str, **fields: object) -> str:
        outcome = self.run("add_itinerary_item", {"day": day, "title": title, **fields})
        assert not outcome.is_error, outcome.content
        found = re.search(r"\[([0-9a-f]+)\]", outcome.content)
        assert found is not None
        return found.group(1)


def test_the_old_replace_the_whole_text_tool_is_gone(tmp_path: Path) -> None:
    assert sorted(Setup(tmp_path).tools) == [
        "add_itinerary_item",
        "change_itinerary_item",
        "get_itinerary",
        "remove_itinerary_item",
        "restore_itinerary",
        "set_itinerary_trip",
    ]


def test_get_says_so_when_nothing_is_saved(tmp_path: Path) -> None:
    assert Setup(tmp_path).run("get_itinerary", {}).content == NO_ITINERARY_RESULT


def test_add_keeps_an_item_and_gives_its_id(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    item_id = setup.add(1, "Kiyomizu", start="9:00", end="10:30", place="Kyoto", url="https://a.jp")
    items = setup.book.get(GROUP).items  # type: ignore[union-attr]
    assert [(i.id, i.day, i.start, i.end, i.place) for i in items] == [
        (item_id, 1, "09:00", "10:30", "Kyoto")
    ]


def test_get_lists_the_trip_the_items_with_ids_and_the_earlier_versions(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.run("set_itinerary_trip", {"title": "Kyoto", "start_date": "2026-11-23"})
    lunch = setup.add(1, "Lunch", start="12:00")
    setup.add(2, "Free")
    content = setup.run("get_itinerary", {}).content
    assert content.startswith("Trip: Kyoto; day 1 is 2026-11-23; saved ")
    assert "11/23(月) 1日目\n  [" + lunch + "] 12:00- Lunch" in content
    assert "11/24(火) 2日目" in content and "時間未定 Free" in content
    assert "Earlier version 1:" in content and "Earlier version 2:" in content


def test_get_shows_the_memo_of_the_earlier_shape_for_the_model_to_turn_into_items(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path)
    setup.book.update(GROUP, "1日目 (11/23)\nKyoto")
    content = setup.run("get_itinerary", {}).content
    assert "Earlier memo" in content and content.endswith("1日目 (11/23)\nKyoto")


def test_add_refuses_bad_fields_and_adds_nothing(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    bad_inputs = [
        None,
        {},
        {"title": "no day"},
        {"day": 1},
        {"day": 0, "title": "x"},
        {"day": 1, "title": "x", "start": "9am"},
        {"day": 1, "title": "x", "end": "10:00"},
        {"day": 1, "title": "x", "start": "10:00", "end": "09:00"},
        {"day": 1, "title": "x", "start": "10:00", "end": "10:00"},
        {"day": 1, "title": "x", "url": "javascript:alert(1)"},
        {"day": 1, "title": "x" * 61},
    ]
    for tool_input in bad_inputs:
        outcome = setup.run("add_itinerary_item", tool_input)
        assert outcome.is_error and "Nothing was added" in outcome.content, tool_input
    assert setup.book.get(GROUP) is None


def test_add_stops_at_the_most_items_it_keeps(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    for number in range(MAX_ITEM_COUNT):
        setup.book.add_item(GROUP, day=1, title=f"item {number}")
    assert setup.run("add_itinerary_item", {"day": 1, "title": "one more"}).is_error


def test_change_changes_only_what_is_given(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    item_id = setup.add(1, "Lunch", start="12:00", end="13:00", note="n")
    outcome = setup.run("change_itinerary_item", {"id": item_id, "start": "12:30", "end": "13:30"})
    assert not outcome.is_error and "12:30-13:30 Lunch" in outcome.content
    changed = setup.book.get(GROUP).items[0]  # type: ignore[union-attr]
    assert (changed.title, changed.start, changed.end, changed.note) == (
        "Lunch",
        "12:30",
        "13:30",
        "n",
    )


def test_change_with_an_empty_string_clears_a_field_and_clearing_start_clears_end(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path)
    item_id = setup.add(1, "Lunch", start="12:00", end="13:00", note="n")
    setup.run("change_itinerary_item", {"id": item_id, "note": ""})
    setup.run("change_itinerary_item", {"id": item_id, "start": ""})
    changed = setup.book.get(GROUP).items[0]  # type: ignore[union-attr]
    assert (changed.start, changed.end, changed.note) == (None, None, None)


def test_change_refuses_an_unknown_id_a_bad_field_and_an_end_before_the_start(
    tmp_path: Path,
) -> None:
    setup = Setup(tmp_path)
    item_id = setup.add(1, "Lunch", start="12:00", end="13:00")
    assert setup.run("change_itinerary_item", {"id": "zzz", "title": "x"}).is_error
    assert setup.run("change_itinerary_item", {"title": "x"}).is_error
    assert setup.run("change_itinerary_item", {"id": item_id, "day": 99}).is_error
    assert setup.run("change_itinerary_item", {"id": item_id, "title": ""}).is_error
    assert setup.run("change_itinerary_item", {"id": item_id, "end": "11:00"}).is_error
    assert setup.book.get(GROUP).items[0].end == "13:00"  # type: ignore[union-attr]


def test_change_to_what_the_item_already_is_is_not_an_error(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    item_id = setup.add(1, "Lunch")
    outcome = setup.run("change_itinerary_item", {"id": item_id, "title": "Lunch"})
    assert not outcome.is_error and "nothing changed" in outcome.content


def test_remove_takes_an_item_out_by_its_id(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    first, second = setup.add(1, "A"), setup.add(1, "B")
    assert not setup.run("remove_itinerary_item", {"id": first}).is_error
    assert [i.id for i in setup.book.get(GROUP).items] == [second]  # type: ignore[union-attr]
    assert setup.run("remove_itinerary_item", {"id": first}).is_error
    assert setup.run("remove_itinerary_item", {}).is_error


def test_set_trip_sets_the_name_and_the_first_day_and_checks_them(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    assert not setup.run(
        "set_itinerary_trip", {"title": "Kyoto", "start_date": "2026-11-23"}
    ).is_error
    saved = setup.book.get(GROUP)
    assert saved is not None and (saved.title, saved.start_date) == ("Kyoto", "2026-11-23")
    for bad in ({}, {"start_date": "11/23"}, {"title": "x" * 61}, None):
        assert setup.run("set_itinerary_trip", bad).is_error
    assert "nothing changed" in setup.run("set_itinerary_trip", {"title": "Kyoto"}).content


def test_restore_puts_an_earlier_version_back(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.add(1, "A")
    setup.add(1, "B")
    assert not setup.run("restore_itinerary", {}).is_error
    assert [i.title for i in setup.book.get(GROUP).items] == ["A"]  # type: ignore[union-attr]
    assert setup.run("restore_itinerary", {"version": 9}).is_error
    assert setup.run("restore_itinerary", {"version": "1"}).is_error
    assert setup.run("restore_itinerary", None).content.startswith("Version 1 is back")


def test_get_with_show_card_sends_the_card_after_the_reply(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.add(1, "Kiyomizu", start="09:00")
    outcome = setup.run("get_itinerary", {"show_card": True})
    assert "card is sent" in outcome.content and len(setup.output.extras) == 1
    extra: OutgoingExtra = setup.output.extras[0]
    link_id = setup.book.link_id(GROUP)
    assert extra.message["type"] == "flex"
    assert f"{LIFF_ID}/itinerary?i={link_id}" in str(extra.message)
    assert extra.record_line.startswith("[予定表]")


def test_get_without_show_card_sends_nothing(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    setup.add(1, "A")
    setup.run("get_itinerary", {})
    setup.run("get_itinerary", {"show_card": "yes"})
    assert setup.output.extras == []


def test_the_card_is_left_out_with_a_reason_when_it_cannot_be_sent(tmp_path: Path) -> None:
    no_page = Setup(tmp_path / "a", liff_id=None)
    no_page.add(1, "A")
    assert "No card was sent" in no_page.run("get_itinerary", {"show_card": True}).content
    assert no_page.output.extras == []

    empty = Setup(tmp_path / "b")
    empty.run("set_itinerary_trip", {"title": "Trip"})
    assert "nothing on the itinerary" in empty.run("get_itinerary", {"show_card": True}).content

    full = Setup(tmp_path / "c")
    full.add(1, "A")
    for _ in range(MAX_EXTRA_MESSAGES):
        full.output.add(OutgoingExtra({"type": "text"}, "x"))
    assert "No card was sent" in full.run("get_itinerary", {"show_card": True}).content
    assert len(full.output.extras) == MAX_EXTRA_MESSAGES
