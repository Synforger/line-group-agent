import json
from datetime import datetime, timedelta
from pathlib import Path

from line_group_agent.reminders.reminder import GROUP_TIME_ZONE, ReminderState, month_of
from line_group_agent.reminders.reminder_book import REMINDERS_FILE_NAME, ReminderBook
from tests.world import GROUP, Clock

LATER = datetime(2026, 11, 20, 21, 0, tzinfo=GROUP_TIME_ZONE)


def book_for(tmp_path: Path) -> tuple[ReminderBook, Clock]:
    clock = Clock()
    return ReminderBook(tmp_path, clock), clock


def file_of(tmp_path: Path, group: str = GROUP) -> Path:
    return tmp_path / "groups" / group / REMINDERS_FILE_NAME


def test_a_reminder_is_kept_with_a_new_id_each_time(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    first = book.add(GROUP, "gather", LATER, ("Aki",))
    second = book.add(GROUP, "eat", LATER + timedelta(hours=1), ())
    assert (first.id, second.id) == ("r1", "r2")
    assert book.list_pending(GROUP) == [first, second]
    saved = json.loads(file_of(tmp_path).read_text(encoding="utf-8"))
    assert saved["reminders"][0] == {
        "id": "r1",
        "text": "gather",
        "due_at": "2026-11-20T21:00+09:00",
        "names": ["Aki"],
        "created_at": "2026-11-18T12:00:00+09:00",
        "state": "pending",
        "attempts": 0,
    }


def test_the_waiting_reminders_are_listed_soonest_first(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    late = book.add(GROUP, "late", LATER + timedelta(days=1), ())
    early = book.add(GROUP, "early", LATER, ())
    assert book.list_pending(GROUP) == [early, late]


def test_an_id_is_not_used_again_after_a_cancel(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    book.add(GROUP, "a", LATER, ())
    assert book.cancel(GROUP, "r1") is not None
    assert book.add(GROUP, "b", LATER, ()).id == "r2"


def test_cancel_removes_a_waiting_reminder_and_only_that(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    book.add(GROUP, "a", LATER, ())
    book.add(GROUP, "b", LATER, ())
    removed = book.cancel(GROUP, " r1 ")
    assert removed is not None and removed.text == "a"
    assert [r.id for r in book.list_pending(GROUP)] == ["r2"]
    assert book.cancel(GROUP, "r1") is None
    assert book.cancel(GROUP, "r9") is None


def test_a_finished_reminder_cannot_be_cancelled_and_is_not_waiting(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    book.add(GROUP, "a", LATER, ())
    book.finish(GROUP, "r1", ReminderState.SENT)
    assert book.list_pending(GROUP) == [] and book.cancel(GROUP, "r1") is None


def test_due_returns_the_waiting_reminders_of_every_group_whose_time_has_come(
    tmp_path: Path,
) -> None:
    book, _ = book_for(tmp_path)
    book.add(GROUP, "later", LATER + timedelta(hours=2), ())
    book.add(GROUP, "now", LATER, ())
    book.add("Cother", "earlier", LATER - timedelta(hours=1), ())
    found = book.due(LATER)
    assert [(due.group_id, due.reminder.text) for due in found] == [
        ("Cother", "earlier"),
        (GROUP, "now"),
    ]


def test_a_failed_attempt_is_counted_and_the_reminder_keeps_waiting(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    book.add(GROUP, "a", LATER, ())
    book.note_failed_attempt(GROUP, "r1")
    [waiting] = book.list_pending(GROUP)
    assert waiting.attempts == 1


def test_the_month_count_holds_waiting_and_sent_reminders_of_that_month(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    for number in range(4):
        book.add(GROUP, f"n{number}", LATER + timedelta(minutes=number), ())
    book.add(GROUP, "december", datetime(2026, 12, 1, 9, 0, tzinfo=GROUP_TIME_ZONE), ())
    book.finish(GROUP, "r2", ReminderState.SENT)
    book.finish(GROUP, "r3", ReminderState.MISSED)
    book.cancel(GROUP, "r4")
    assert book.count_booked(GROUP, "2026-11") == 2
    assert book.count_booked(GROUP, month_of(datetime(2026, 12, 1, tzinfo=GROUP_TIME_ZONE))) == 1


def test_a_finished_reminder_is_forgotten_after_forty_days(tmp_path: Path) -> None:
    book, clock = book_for(tmp_path)
    book.add(GROUP, "old", LATER, ())
    book.finish(GROUP, "r1", ReminderState.SENT)
    clock.advance(days=45)
    book.add(GROUP, "new", LATER + timedelta(days=45), ())
    saved = json.loads(file_of(tmp_path).read_text(encoding="utf-8"))
    assert [row["text"] for row in saved["reminders"]] == ["new"]


def test_a_damaged_file_reads_as_no_reminders_and_a_bad_row_is_left_out(tmp_path: Path) -> None:
    book, _ = book_for(tmp_path)
    path = file_of(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("{cut", encoding="utf-8")
    assert book.list_pending(GROUP) == []
    good = {
        "id": "r1",
        "text": "a",
        "due_at": LATER.isoformat(),
        "names": [],
        "created_at": LATER.isoformat(),
        "state": "pending",
        "attempts": 0,
    }
    rows = [good, {**good, "id": "r2", "due_at": "soon"}, {**good, "id": "r3", "state": "x"}, "x"]
    path.write_text(json.dumps({"last_number": "many", "reminders": rows}), encoding="utf-8")
    assert [r.id for r in book.list_pending(GROUP)] == ["r1"]
    assert book.add(GROUP, "b", LATER, ()).id == "r2"
