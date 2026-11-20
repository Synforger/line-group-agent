from datetime import datetime, timedelta

import pytest

from line_group_agent.reminders.reminder import GROUP_TIME_ZONE
from line_group_agent.reminders.reminder_input import (
    MAX_DAYS_AHEAD,
    MAX_NAMES,
    TEXT_MAX_CHARS,
    ReminderInputError,
    due_time_of,
    names_of,
    text_of,
)

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=GROUP_TIME_ZONE)


def test_a_time_without_an_offset_is_the_groups_local_time() -> None:
    assert due_time_of("2026-11-22T21:00", NOW) == datetime(
        2026, 11, 22, 21, 0, tzinfo=GROUP_TIME_ZONE
    )


def test_a_time_with_an_offset_is_moved_to_the_groups_time_zone() -> None:
    due = due_time_of("2026-11-22T12:00:00+00:00", NOW)
    assert (due.hour, due.utcoffset()) == (21, timedelta(hours=9))


def test_seconds_are_dropped() -> None:
    assert due_time_of("2026-11-22T21:00:45", NOW).second == 0


@pytest.mark.parametrize(
    "raw", [None, 5, "", "tomorrow", "2026-11-22", "2026-13-40T10:00", "2026-11-22 25:00"]
)
def test_something_that_is_not_a_date_and_time_is_refused(raw: object) -> None:
    with pytest.raises(ReminderInputError, match="ISO date and time"):
        due_time_of(raw, NOW)


def test_a_time_that_has_passed_or_is_now_is_refused_and_the_error_gives_the_time_now() -> None:
    with pytest.raises(ReminderInputError, match=r"already passed.*2026-11-18 12:00"):
        due_time_of("2026-11-18T12:00", NOW)
    with pytest.raises(ReminderInputError, match="already passed"):
        due_time_of("2026-11-17T09:00", NOW)


def test_the_limit_is_sixty_days_ahead() -> None:
    last = NOW + timedelta(days=MAX_DAYS_AHEAD)
    assert due_time_of(last.isoformat(), NOW) == last
    with pytest.raises(ReminderInputError, match="60 days"):
        due_time_of((last + timedelta(minutes=1)).isoformat(), NOW)


def test_the_text_is_trimmed_and_must_be_there_and_short() -> None:
    assert text_of("  gather at 21:00 \n") == "gather at 21:00"
    for raw in (None, "", "   ", 3):
        with pytest.raises(ReminderInputError, match="text is required"):
            text_of(raw)
    with pytest.raises(ReminderInputError, match="over 300"):
        text_of("a" * (TEXT_MAX_CHARS + 1))
    assert len(text_of("a" * TEXT_MAX_CHARS)) == TEXT_MAX_CHARS


def test_names_are_cleaned_and_kept_once() -> None:
    assert names_of(None) == () and names_of([]) == ()
    assert names_of([" @Aki ", "Ben", "Aki", ""]) == ("Aki", "Ben")


@pytest.mark.parametrize("raw", ["Aki", [1], [["Aki"]], ["a" * 41]])
def test_a_who_that_is_not_a_list_of_names_is_refused(raw: object) -> None:
    with pytest.raises(ReminderInputError):
        names_of(raw)


def test_too_many_names_are_refused() -> None:
    with pytest.raises(ReminderInputError, match="at most 10"):
        names_of([f"n{number}" for number in range(MAX_NAMES + 1)])
