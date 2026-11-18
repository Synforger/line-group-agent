from datetime import datetime, timedelta, timezone
from pathlib import Path

from line_group_agent.polls.poll_book import MAX_POLLS_KEPT, PollBook, VoteResult

GROUP = "Cgroup"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone(timedelta(hours=9)))


def book(tmp_path: Path) -> PollBook:
    return PollBook(tmp_path, lambda: NOW)


def test_polls_are_numbered_in_the_group_and_kept_in_a_file(tmp_path: Path) -> None:
    first = book(tmp_path).create(GROUP, "Where?", ["Kyoto", "Osaka"])
    second = book(tmp_path).create(GROUP, "When?", ["Sat", "Sun"], multiple=True)
    assert (first.id, second.id) == ("p1", "p2")
    assert (tmp_path / "groups" / GROUP / "polls.json").exists()
    kept = book(tmp_path).get(GROUP, "p2")
    assert kept is not None and kept.multiple and kept.question == "When?"
    assert kept.created_at == "2026-11-18T12:00:00+09:00"
    assert [o.label for o in kept.options] == ["Sat", "Sun"]


def test_another_group_has_its_own_numbers(tmp_path: Path) -> None:
    book(tmp_path).create(GROUP, "Where?", ["A", "B"])
    assert book(tmp_path).create("Cother", "Why?", ["A", "B"]).id == "p1"


def test_without_an_id_the_newest_open_poll_is_found_else_the_newest(tmp_path: Path) -> None:
    polls = book(tmp_path)
    assert polls.get(GROUP) is None
    polls.create(GROUP, "One", ["A", "B"])
    polls.create(GROUP, "Two", ["A", "B"])
    polls.close(GROUP, "p2")
    found = polls.get(GROUP)
    assert found is not None and found.id == "p1"
    polls.close(GROUP, "p1")
    found = polls.get(GROUP)
    assert found is not None and found.id == "p2"


def test_an_id_may_be_written_as_a_bare_number_or_in_capitals(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "One", ["A", "B"])
    for written in ("1", "P1", " p1 "):
        found = polls.get(GROUP, written)
        assert found is not None and found.id == "p1"
    assert polls.get(GROUP, "p9") is None


def test_one_vote_each_and_a_second_press_on_the_same_option_changes_nothing(
    tmp_path: Path,
) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Where?", ["Kyoto", "Osaka"])
    assert polls.vote(GROUP, "p1", 0, "U1", "Aki") is VoteResult.COUNTED
    assert polls.vote(GROUP, "p1", 0, "U1", "Aki") is VoteResult.UNCHANGED
    assert polls.vote(GROUP, "p1", 0, "U1", "Aki") is VoteResult.UNCHANGED
    poll = polls.get(GROUP, "p1")
    assert poll is not None and [len(o.voters) for o in poll.options] == [1, 0]


def test_in_a_single_pick_poll_another_option_moves_the_vote(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Where?", ["Kyoto", "Osaka"])
    polls.vote(GROUP, "p1", 0, "U1", "Aki")
    polls.vote(GROUP, "p1", 0, "U2", "Sora")
    assert polls.vote(GROUP, "p1", 1, "U1", "Aki") is VoteResult.COUNTED
    poll = polls.get(GROUP, "p1")
    assert poll is not None
    assert [[v.name for v in o.voters] for o in poll.options] == [["Sora"], ["Aki"]]


def test_in_a_multiple_poll_each_option_is_its_own_switch(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Which days?", ["Sat", "Sun", "Mon"], multiple=True)
    polls.vote(GROUP, "p1", 0, "U1", "Aki")
    polls.vote(GROUP, "p1", 2, "U1", "Aki")
    polls.vote(GROUP, "p1", 0, "U1", "Aki")
    poll = polls.get(GROUP, "p1")
    assert poll is not None
    assert [[v.user_id for v in o.voters] for o in poll.options] == [[], [], ["U1"]]


def test_in_a_multiple_poll_a_second_press_takes_the_pick_back(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Which days?", ["Sat", "Sun"], multiple=True)
    assert polls.vote(GROUP, "p1", 0, "U1", "Aki") is VoteResult.COUNTED
    assert polls.vote(GROUP, "p1", 0, "U1", "Aki") is VoteResult.WITHDRAWN
    poll = polls.get(GROUP, "p1")
    assert poll is not None and [len(o.voters) for o in poll.options] == [0, 0]


def test_withdrawing_takes_back_every_vote_of_that_member_only(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Which days?", ["Sat", "Sun"], multiple=True)
    for option_index in (0, 1):
        polls.vote(GROUP, "p1", option_index, "U1", "Aki")
    polls.vote(GROUP, "p1", 0, "U2", "Sora")
    assert polls.withdraw(GROUP, "p1", "U1") is VoteResult.WITHDRAWN
    poll = polls.get(GROUP, "p1")
    assert poll is not None
    assert [[v.user_id for v in o.voters] for o in poll.options] == [["U2"], []]


def test_withdrawing_without_a_vote_or_from_a_closed_or_unknown_poll_is_ignored(
    tmp_path: Path,
) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Where?", ["Kyoto", "Osaka"])
    assert polls.withdraw(GROUP, "p1", "U1") is VoteResult.IGNORED
    assert polls.withdraw(GROUP, "p9", "U1") is VoteResult.IGNORED
    polls.vote(GROUP, "p1", 0, "U1", "Aki")
    polls.close(GROUP, "p1")
    assert polls.withdraw(GROUP, "p1", "U1") is VoteResult.IGNORED
    poll = polls.get(GROUP, "p1")
    assert poll is not None and len(poll.options[0].voters) == 1


def test_a_vote_that_cannot_count_is_ignored(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Where?", ["Kyoto", "Osaka"])
    assert polls.vote(GROUP, "p9", 0, "U1", None) is VoteResult.IGNORED
    assert polls.vote(GROUP, "p1", 2, "U1", None) is VoteResult.IGNORED
    assert polls.vote(GROUP, "p1", -1, "U1", None) is VoteResult.IGNORED
    polls.close(GROUP, "p1")
    assert polls.vote(GROUP, "p1", 0, "U1", None) is VoteResult.IGNORED


def test_closing_keeps_the_votes_and_closing_twice_finds_nothing(tmp_path: Path) -> None:
    polls = book(tmp_path)
    polls.create(GROUP, "Where?", ["Kyoto", "Osaka"])
    polls.vote(GROUP, "p1", 0, "U1", "Aki")
    closed = polls.close(GROUP)
    assert closed is not None and closed.is_closed and len(closed.options[0].voters) == 1
    assert polls.close(GROUP) is None
    assert polls.close(GROUP, "p1") is None


def test_only_the_newest_polls_are_kept_and_the_numbers_go_on(tmp_path: Path) -> None:
    polls = book(tmp_path)
    for _ in range(MAX_POLLS_KEPT + 3):
        polls.create(GROUP, "Q", ["A", "B"])
    assert polls.get(GROUP, "p1") is None and polls.get(GROUP, "p4") is not None
    assert polls.create(GROUP, "Q", ["A", "B"]).id == f"p{MAX_POLLS_KEPT + 4}"


def test_a_damaged_file_reads_as_no_polls(tmp_path: Path) -> None:
    folder = tmp_path / "groups" / GROUP
    folder.mkdir(parents=True)
    (folder / "polls.json").write_text("{not json")
    assert book(tmp_path).get(GROUP) is None
    assert book(tmp_path).create(GROUP, "Q", ["A", "B"]).id == "p1"


def test_a_group_id_that_is_not_letters_and_digits_is_refused(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="group id"):
        book(tmp_path).get("../x")
