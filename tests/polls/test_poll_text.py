from line_group_agent.polls.poll import KIND_DATE, Poll, PollOption, Voter
from line_group_agent.polls.poll_text import (
    format_picks_line,
    format_poll_results,
    poll_record_line,
)


def poll(**changes: object) -> Poll:
    base = Poll(
        id="p1",
        kind="choice",
        question="Where?",
        options=[
            PollOption("Kyoto", [Voter("U1", "Aki"), Voter("U2", None)]),
            PollOption("Osaka"),
        ],
        multiple=False,
        is_closed=False,
        created_at="t",
    )
    for key, value in changes.items():
        setattr(base, key, value)
    return base


def test_the_record_line_names_the_poll_and_its_options() -> None:
    assert poll_record_line(poll()) == "[投票] p1 Where? 1. Kyoto / 2. Osaka"


def test_a_date_poll_has_its_own_label() -> None:
    assert poll_record_line(poll(kind=KIND_DATE)).startswith("[日程] p1 ")


def test_the_results_give_counts_names_and_the_number_of_voters() -> None:
    assert format_poll_results(poll()) == (
        "Poll p1 (open, one vote each): Where?\n"
        "1. Kyoto: 2 (Aki, someone)\n"
        "2. Osaka: 0\n"
        "2 member(s) have voted."
    )


def test_a_closed_multiple_poll_says_so_and_counts_each_member_once() -> None:
    both = [PollOption("Sat", [Voter("U1", "Aki")]), PollOption("Sun", [Voter("U1", "Aki")])]
    text = format_poll_results(poll(options=both, multiple=True, is_closed=True))
    assert text.splitlines()[0] == "Poll p1 (closed, pick several): Where?"
    assert text.endswith("1 member(s) have voted.")


def test_a_date_poll_is_described_as_marking_dates() -> None:
    assert "date poll" in format_poll_results(poll(kind=KIND_DATE)).splitlines()[0]


def test_the_picks_line_names_the_member_and_lists_their_options_in_the_polls_order() -> None:
    days = [
        PollOption("11/23", [Voter("U1", "Aki")]),
        PollOption("11/24", [Voter("U2", "Sora")]),
        PollOption("11/25", [Voter("U1", "Aki"), Voter("U2", "Sora")]),
    ]
    assert format_picks_line(poll(options=days), "U1", "Aki") == "Aki: 11/23、11/25"


def test_the_picks_line_says_none_when_nothing_is_picked() -> None:
    assert format_picks_line(poll(), "U9", "Mio") == "Mio: なし"


def test_the_picks_line_without_a_name_speaks_to_the_member() -> None:
    assert format_picks_line(poll(), "U1", None) == "あなた: Kyoto"
