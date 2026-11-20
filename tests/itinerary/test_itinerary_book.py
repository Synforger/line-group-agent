import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from line_group_agent.itinerary.itinerary_book import MAX_VERSIONS_KEPT, ItineraryBook

GROUP = "Cgroup"
OTHER_GROUP = "Cother"
TOKYO = timezone(timedelta(hours=9))
LEGACY_TEXT = "1日目 (11/23)\nKyoto"


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 18, 12, 0, tzinfo=TOKYO)

    def __call__(self) -> datetime:
        self.moment += timedelta(minutes=1)
        return self.moment


def make_book(tmp_path: Path) -> ItineraryBook:
    return ItineraryBook(tmp_path, Clock())


def write_file(tmp_path: Path, document: object, group: str = GROUP) -> Path:
    folder = tmp_path / "groups" / group
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "itinerary.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_nothing_is_saved_at_first(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    assert book.get(GROUP) is None and book.versions(GROUP) == []
    assert book.link_id(GROUP) is None


def test_an_item_is_kept_with_a_short_id_and_when_it_was_saved(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    item = book.add_item(GROUP, day=1, title="Kiyomizu", start="09:00", place="Kyoto")
    saved = book.get(GROUP)
    assert saved is not None and saved.items == (item,)
    assert len(item.id) == 6 and item.end is None and item.note is None
    assert saved.saved_at == "2026-11-18T12:01:00+09:00"
    assert book.versions(GROUP) == []


def test_every_change_keeps_the_state_it_replaces_newest_first(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    first = book.add_item(GROUP, day=1, title="A")
    book.add_item(GROUP, day=1, title="B")
    book.change_item(GROUP, first.id, {"title": "A2"})
    versions = book.versions(GROUP)
    assert [[item.title for item in version.items] for version in versions] == [["A", "B"], ["A"]]


def test_a_change_names_only_the_fields_it_changes_and_none_clears_one(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    item = book.add_item(GROUP, day=1, title="A", start="09:00", end="10:00", note="n")
    changed = book.change_item(GROUP, item.id, {"day": 2, "end": None})
    assert changed is not None
    assert (changed.day, changed.title, changed.start, changed.end, changed.note) == (
        2,
        "A",
        "09:00",
        None,
        "n",
    )
    assert book.get(GROUP).items == (changed,)  # type: ignore[union-attr]


def test_a_change_to_the_values_it_already_has_writes_nothing(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    item = book.add_item(GROUP, day=1, title="A")
    assert book.change_item(GROUP, item.id, {"title": "A"}) == item
    assert book.versions(GROUP) == []
    assert not book.change_trip(GROUP, {"title": ""})
    assert book.versions(GROUP) == []


def test_an_unknown_id_changes_and_removes_nothing(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    assert book.change_item(GROUP, "nope", {"title": "x"}) is None
    book.add_item(GROUP, day=1, title="A")
    assert book.change_item(GROUP, "nope", {"title": "x"}) is None
    assert book.remove_item(GROUP, "nope") is None
    assert len(book.get(GROUP).items) == 1  # type: ignore[union-attr]


def test_removing_an_item_keeps_the_others_and_the_version(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    first = book.add_item(GROUP, day=1, title="A")
    second = book.add_item(GROUP, day=2, title="B")
    assert book.remove_item(GROUP, first.id) == first
    assert book.get(GROUP).items == (second,)  # type: ignore[union-attr]
    assert [len(version.items) for version in book.versions(GROUP)] == [2, 1]


def test_the_trip_name_and_first_day_can_be_set_before_any_item(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    assert book.change_trip(GROUP, {"title": "Kyoto trip", "start_date": "2026-11-23"})
    saved = book.get(GROUP)
    assert saved is not None and (saved.title, saved.start_date, saved.items) == (
        "Kyoto trip",
        "2026-11-23",
        (),
    )
    assert book.change_trip(GROUP, {"start_date": None})
    assert book.get(GROUP).start_date is None  # type: ignore[union-attr]


def test_only_the_last_five_replaced_versions_are_kept(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    for number in range(1, 10):
        book.add_item(GROUP, day=1, title=f"v{number}")
    assert len(book.versions(GROUP)) == MAX_VERSIONS_KEPT
    assert [len(version.items) for version in book.versions(GROUP)] == [8, 7, 6, 5, 4]


def test_restore_puts_an_earlier_version_back_and_keeps_the_state_it_replaces(
    tmp_path: Path,
) -> None:
    book = make_book(tmp_path)
    book.add_item(GROUP, day=1, title="A")
    book.add_item(GROUP, day=1, title="B")
    restored = book.restore(GROUP, 1)
    assert restored is not None and [item.title for item in restored.items] == ["A"]
    assert [len(version.items) for version in book.versions(GROUP)] == [2, 1]
    assert book.restore(GROUP, 1) is not None
    assert [item.title for item in book.get(GROUP).items] == ["A", "B"]  # type: ignore[union-attr]


def test_restore_refuses_a_version_that_is_not_there(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    assert book.restore(GROUP, 1) is None
    book.add_item(GROUP, day=1, title="A")
    book.add_item(GROUP, day=1, title="B")
    assert [book.restore(GROUP, n) for n in (0, 2, -1)] == [None, None, None]


def test_restore_keeps_the_link_so_a_shared_page_still_opens(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    book.add_item(GROUP, day=1, title="A")
    link_id = book.link_id(GROUP)
    book.add_item(GROUP, day=1, title="B")
    book.restore(GROUP, 1)
    assert book.link_id(GROUP) == link_id


def test_a_file_in_the_earlier_shape_reads_as_a_memo_with_no_items(tmp_path: Path) -> None:
    write_file(
        tmp_path,
        {
            "text": LEGACY_TEXT,
            "saved_at": "2026-11-17T09:00:00+09:00",
            "versions": [{"text": "older", "saved_at": "2026-11-16T09:00:00+09:00"}],
        },
    )
    book = make_book(tmp_path)
    saved = book.get(GROUP)
    assert saved is not None and saved.items == ()
    assert saved.legacy_text == LEGACY_TEXT and saved.text == LEGACY_TEXT
    assert saved.saved_at == "2026-11-17T09:00:00+09:00"
    assert [version.legacy_text for version in book.versions(GROUP)] == ["older"]


def test_changing_an_itinerary_of_the_earlier_shape_keeps_its_text_and_the_old_state(
    tmp_path: Path,
) -> None:
    path = write_file(tmp_path, {"text": LEGACY_TEXT, "saved_at": "2026-11-17T09:00:00+09:00"})
    book = make_book(tmp_path)
    book.add_item(GROUP, day=1, title="Kiyomizu")
    saved = book.get(GROUP)
    assert saved is not None and saved.legacy_text == LEGACY_TEXT and len(saved.items) == 1
    assert [version.legacy_text for version in book.versions(GROUP)] == [LEGACY_TEXT]
    assert json.loads(path.read_text())["legacy_text"] == LEGACY_TEXT
    assert "text" not in json.loads(path.read_text())


def test_the_link_id_is_made_once_and_finds_the_itinerary_again(tmp_path: Path) -> None:
    write_file(tmp_path, {"text": LEGACY_TEXT, "saved_at": ""})
    book = make_book(tmp_path)
    link_id = book.link_id(GROUP)
    assert link_id is not None and len(link_id) >= 16
    assert book.link_id(GROUP) == link_id
    assert book.get(GROUP).legacy_text == LEGACY_TEXT  # type: ignore[union-attr]
    found = book.find_by_link_id(link_id)
    assert found is not None and found.group_id == GROUP


def test_each_group_has_its_own_link_and_a_guess_finds_nothing(tmp_path: Path) -> None:
    book = make_book(tmp_path)
    book.add_item(GROUP, day=1, title="A")
    book.add_item(OTHER_GROUP, day=1, title="B")
    mine, theirs = book.link_id(GROUP), book.link_id(OTHER_GROUP)
    assert mine != theirs and mine and theirs
    assert book.find_by_link_id(theirs).group_id == OTHER_GROUP  # type: ignore[union-attr]
    for guess in ("", "short", "x" * 22, "../" * 8, mine[:-1] + ("A" if mine[-1] != "A" else "B")):
        assert book.find_by_link_id(guess) is None


def test_a_link_id_that_was_not_made_here_is_not_kept(tmp_path: Path) -> None:
    write_file(tmp_path, {"title": "t", "items": [], "link_id": "short"})
    book = make_book(tmp_path)
    assert book.get(GROUP).link_id == ""  # type: ignore[union-attr]
    assert book.find_by_link_id("short") is None


def test_an_item_that_cannot_be_read_is_dropped_and_the_others_stay(tmp_path: Path) -> None:
    good = {"id": "a1", "day": 1, "title": "Good", "start": "9:00", "url": "https://example.com/x"}
    write_file(
        tmp_path,
        {
            "title": "t",
            "items": [
                good,
                {"id": "b2", "day": 0, "title": "bad day"},
                {"id": "c3", "day": 1, "title": ""},
                {"id": "d4", "day": 1, "title": "bad time", "start": "25:00"},
                {"id": "e5", "day": 1, "title": "javascript", "url": "javascript:alert(1)"},
                {"day": 1, "title": "no id"},
                "text",
            ],
        },
    )
    items = make_book(tmp_path).get(GROUP).items  # type: ignore[union-attr]
    assert [item.id for item in items] == ["a1"]
    assert items[0].start == "09:00"


def test_a_damaged_file_reads_as_no_itinerary_and_can_be_replaced(tmp_path: Path) -> None:
    path = write_file(tmp_path, [1, 2])
    book = make_book(tmp_path)
    assert book.get(GROUP) is None and book.versions(GROUP) == []
    book.add_item(GROUP, day=1, title="fresh")
    assert json.loads(path.read_text())["items"][0]["title"] == "fresh"
