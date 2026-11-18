import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from line_group_agent.itinerary.itinerary_book import MAX_VERSIONS_KEPT, ItineraryBook

GROUP = "Cgroup"
TOKYO = timezone(timedelta(hours=9))


class Clock:
    def __init__(self) -> None:
        self.moment = datetime(2026, 11, 18, 12, 0, tzinfo=TOKYO)

    def __call__(self) -> datetime:
        self.moment += timedelta(minutes=1)
        return self.moment


def test_nothing_is_saved_at_first(tmp_path: Path) -> None:
    book = ItineraryBook(tmp_path, Clock())
    assert book.get(GROUP) is None and book.versions(GROUP) == []


def test_an_update_saves_the_text_and_when(tmp_path: Path) -> None:
    book = ItineraryBook(tmp_path, Clock())
    assert book.update(GROUP, "1日目 (11/23)\nKyoto")
    saved = book.get(GROUP)
    assert saved is not None and saved.text == "1日目 (11/23)\nKyoto"
    assert saved.saved_at == "2026-11-18T12:01:00+09:00"
    assert book.versions(GROUP) == []
    assert (tmp_path / "groups" / GROUP / "itinerary.json").exists()


def test_an_update_keeps_the_version_it_replaces_newest_first(tmp_path: Path) -> None:
    book = ItineraryBook(tmp_path, Clock())
    for text in ("v1", "v2", "v3"):
        book.update(GROUP, text)
    assert [v.text for v in book.versions(GROUP)] == ["v2", "v1"]
    current = book.get(GROUP)
    assert current is not None and current.text == "v3"


def test_only_the_last_five_replaced_versions_are_kept(tmp_path: Path) -> None:
    book = ItineraryBook(tmp_path, Clock())
    for number in range(1, 10):
        book.update(GROUP, f"v{number}")
    assert [v.text for v in book.versions(GROUP)] == ["v8", "v7", "v6", "v5", "v4"]
    assert len(book.versions(GROUP)) == MAX_VERSIONS_KEPT


def test_saving_the_same_text_again_writes_nothing(tmp_path: Path) -> None:
    book = ItineraryBook(tmp_path, Clock())
    book.update(GROUP, "same")
    assert not book.update(GROUP, "same")
    assert book.versions(GROUP) == []


def test_a_damaged_file_reads_as_no_itinerary_and_can_be_replaced(tmp_path: Path) -> None:
    folder = tmp_path / "groups" / GROUP
    folder.mkdir(parents=True)
    (folder / "itinerary.json").write_text("[1, 2]")
    book = ItineraryBook(tmp_path, Clock())
    assert book.get(GROUP) is None
    assert book.update(GROUP, "fresh")
    assert json.loads((folder / "itinerary.json").read_text())["text"] == "fresh"
