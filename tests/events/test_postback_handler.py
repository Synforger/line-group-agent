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
):
    handler.handle(GROUP, data=data, user_id=user, display_name="Aki", event_id=event_id)


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
    press(handler, "poll:p1:0", event_id="E1")
    press(handler, "poll:p1:0", event_id="E1")
    assert voters(book) == [["U1"], []]
    press(handler, "poll:p1:0", event_id="E2")
    assert voters(book) == [[], []]


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
