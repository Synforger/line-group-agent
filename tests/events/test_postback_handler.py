import logging
from datetime import datetime
from pathlib import Path

import pytest

from line_group_agent.events.postback_handler import PostbackHandler
from line_group_agent.polls.poll_book import PollBook

GROUP = "Cgroup"


def setup(tmp_path: Path) -> tuple[PostbackHandler, PollBook]:
    book = PollBook(tmp_path, lambda: datetime(2026, 11, 18, 12, 0).astimezone())
    book.create(GROUP, "Where?", ["Kyoto", "Osaka"])
    return PostbackHandler(book), book


def press(
    handler: PostbackHandler, data: str, user: str | None = "U1", event_id: str | None = None
) -> str | None:
    return handler.handle(GROUP, data=data, user_id=user, display_name="Aki", event_id=event_id)


def voters(book: PollBook) -> list[list[str]]:
    poll = book.get(GROUP, "p1")
    assert poll is not None
    return [[v.user_id for v in option.voters] for option in poll.options]


def test_a_press_on_a_poll_button_is_counted(tmp_path: Path) -> None:
    handler, book = setup(tmp_path)
    press(handler, "poll:p1:1")
    assert voters(book) == [[], ["U1"]]


def test_the_same_event_delivered_again_is_not_counted_twice(tmp_path: Path) -> None:
    handler, book = setup(tmp_path)
    book.create(GROUP, "Which days?", ["Sat", "Sun"], multiple=True)
    assert press(handler, "poll:p2:0", event_id="E1") == "Aki: Sat"
    assert press(handler, "poll:p2:0", event_id="E1") is None
    assert press(handler, "poll:p2:0", event_id="E2") == "Aki: なし"


def test_a_second_press_on_the_same_option_of_a_one_pick_poll_keeps_the_vote(
    tmp_path: Path,
) -> None:
    handler, book = setup(tmp_path)
    press(handler, "poll:p1:0", event_id="E1")
    press(handler, "poll:p1:0", event_id="E2")
    assert voters(book) == [["U1"], []]
    press(handler, "poll:p1:1", event_id="E3")
    assert voters(book) == [[], ["U1"]]


def test_a_one_pick_poll_gets_no_answer_line(tmp_path: Path) -> None:
    handler, _ = setup(tmp_path)
    assert press(handler, "poll:p1:0") is None
    assert press(handler, "poll:p1:0") is None
    assert press(handler, "poll:p1:1") is None


def test_a_poll_that_allows_several_picks_answers_with_what_the_member_has_picked(
    tmp_path: Path,
) -> None:
    handler, book = setup(tmp_path)
    book.create(GROUP, "Which days?", ["Sat", "Sun", "Mon"], multiple=True)
    assert press(handler, "poll:p2:2") == "Aki: Mon"
    assert press(handler, "poll:p2:0") == "Aki: Sat、Mon"
    assert press(handler, "poll:p2:2") == "Aki: Sat"
    assert press(handler, "poll:p2:0") == "Aki: なし"


def test_a_date_poll_answers_too_and_other_members_picks_are_not_listed(tmp_path: Path) -> None:
    handler, book = setup(tmp_path)
    book.create(GROUP, "Trip day", ["11/23", "11/24"], kind="date", multiple=True)
    handler.handle(GROUP, data="poll:p2:1", user_id="U2", display_name="Sora", event_id=None)
    assert press(handler, "poll:p2:0") == "Aki: 11/23"


def test_a_press_that_cannot_count_gets_no_answer(tmp_path: Path) -> None:
    handler, book = setup(tmp_path)
    book.create(GROUP, "Which days?", ["Sat", "Sun"], multiple=True)
    assert press(handler, "poll:p2:5") is None
    assert press(handler, "poll:p9:0") is None
    book.close(GROUP, "p2")
    assert press(handler, "poll:p2:0") is None


def test_a_press_without_the_member_id_is_not_counted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    handler, book = setup(tmp_path)
    with caplog.at_level(logging.INFO):
        press(handler, "poll:p1:0", user=None)
    assert voters(book) == [[], []]
    assert "without a user id" in caplog.text


@pytest.mark.parametrize(
    "data", ["", "other:p1:0", "poll:p1", "poll:p1:x", "poll:p1:0:1", "poll:p1:-1"]
)
def test_data_that_is_not_a_vote_is_ignored(tmp_path: Path, data: str) -> None:
    handler, book = setup(tmp_path)
    press(handler, data)
    assert voters(book) == [[], []]


def test_a_vote_for_a_poll_that_does_not_exist_changes_nothing(tmp_path: Path) -> None:
    handler, book = setup(tmp_path)
    press(handler, "poll:p9:0")
    assert voters(book) == [[], []]
