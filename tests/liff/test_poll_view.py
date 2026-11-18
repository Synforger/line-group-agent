from line_group_agent.liff.poll_view import UNNAMED_VOTER, poll_view_of, unnamed_voter_ids
from line_group_agent.polls.poll import KIND_DATE, Poll, PollOption, Voter


def poll() -> Poll:
    return Poll(
        "p1",
        KIND_DATE,
        "When?",
        [
            PollOption("11/23", [Voter("U1", "Aki"), Voter("U2", None)]),
            PollOption("11/24", [Voter("U2", None), Voter("U3", "")]),
            PollOption("11/25"),
        ],
        multiple=True,
        is_closed=True,
        created_at="t",
        link_id="L" * 22,
    )


def test_the_view_holds_what_the_page_shows_and_nothing_to_find_the_poll_by() -> None:
    view = poll_view_of(poll(), "U1", {"U2": "Ben"})
    assert view == {
        "question": "When?",
        "kind": "date",
        "multiple": True,
        "is_closed": True,
        "voter_count": 3,
        "options": [
            {"label": "11/23", "count": 2, "voters": ["Aki", "Ben"], "mine": True},
            {"label": "11/24", "count": 2, "voters": ["Ben", UNNAMED_VOTER], "mine": False},
            {"label": "11/25", "count": 0, "voters": [], "mine": False},
        ],
    }
    assert "U1" not in str(view) and "L" * 22 not in str(view)


def test_a_member_in_several_options_is_one_voter() -> None:
    assert poll_view_of(poll(), "U9", {})["voter_count"] == 3


def test_a_kept_name_wins_over_a_found_one() -> None:
    view = poll_view_of(poll(), "U9", {"U1": "Someone else"})
    assert view["options"][0]["voters"][0] == "Aki"


def test_voters_without_a_kept_name_are_listed_once_in_order() -> None:
    assert unnamed_voter_ids(poll()) == ["U2", "U3"]
