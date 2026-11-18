import json
import logging
from pathlib import Path

import pytest

from line_group_agent.events.postback_handler import PostbackHandler
from tests.liff.liff_harness import (
    GOOD_TOKEN,
    ISSUER,
    LIFF_ID,
    LOGIN_CHANNEL,
    MEMBER,
    OTHER_MEMBER,
    OTHER_TOKEN,
    OUTSIDER,
    build_liff,
    claims_of,
)
from tests.world import GROUP

LONG_AGO = -7200


def test_the_page_is_served_with_the_liff_id_and_no_group_content(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.polls.vote(GROUP, liff.poll.id, 0, MEMBER, "Aki")
    page = liff.client.get("/liff/")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert f'"{LIFF_ID}"' in page.text
    for content in ("Which?", "Kyoto", "Osaka", "Aki", GROUP, MEMBER, liff.poll.link_id):
        assert content not in page.text


def test_the_page_may_not_be_cached_or_leak_its_address(tmp_path: Path) -> None:
    headers = build_liff(tmp_path).client.get("/liff/").headers
    assert headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"


def test_a_member_gets_the_poll_with_counts_names_and_their_own_pick(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.polls.vote(GROUP, liff.poll.id, 0, OTHER_MEMBER, "Ben")
    liff.polls.vote(GROUP, liff.poll.id, 1, MEMBER, "Aki")
    response = liff.show()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "question": "Which?",
        "kind": "choice",
        "multiple": False,
        "is_closed": False,
        "voter_count": 2,
        "options": [
            {"label": "Kyoto", "count": 1, "voters": ["Ben"], "mine": False},
            {"label": "Osaka", "count": 1, "voters": ["Aki"], "mine": True},
        ],
    }


def test_no_member_id_leaves_the_server(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.polls.vote(GROUP, liff.poll.id, 0, OTHER_MEMBER, "Ben")
    text = liff.show().text + liff.vote(1).text
    assert MEMBER not in text and OTHER_MEMBER not in text and GROUP not in text


def test_a_voter_without_a_kept_name_is_named_from_the_profile_once(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.polls.vote(GROUP, liff.poll.id, 0, OTHER_MEMBER, None)
    liff.polls.vote(GROUP, liff.poll.id, 1, "Ustranger", None)
    options = liff.show().json()["options"]
    assert options[0]["voters"] == ["Ben"] and options[1]["voters"] == ["名前なし"]
    lookups = liff.line.name_lookups
    liff.show()
    assert liff.line.name_lookups == lookups + 1  # only the stranger, whose name LINE lacks


@pytest.mark.parametrize("header", [None, "Basic abc", "Bearer", "Bearer   ", "token-of-member"])
def test_a_request_without_a_bearer_token_is_401(tmp_path: Path, header: str | None) -> None:
    liff = build_liff(tmp_path)
    headers = {"Authorization": header} if header else {}
    body = json.dumps({"p": liff.poll.link_id}).encode()
    response = liff.client.post("/liff/api/poll", content=body, headers=headers)
    assert response.status_code == 401
    assert liff.login.calls == []


def test_a_token_longer_than_any_real_one_is_401_without_asking_line(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    assert liff.show(token="x" * 5000).status_code == 401
    assert liff.login.calls == []


def test_the_token_is_verified_for_the_login_channel(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.show()
    assert liff.login.calls == [(GOOD_TOKEN, LOGIN_CHANNEL)]


def test_a_token_line_refuses_is_401(tmp_path: Path) -> None:
    assert build_liff(tmp_path).show(token="forged").status_code == 401


@pytest.mark.parametrize(
    "changes",
    [
        {"aud": "9999999999"},
        {"exp": LONG_AGO},
        {"iss": "https://elsewhere.example"},
        {"sub": ""},
        {"sub": None},
    ],
)
def test_a_token_with_the_wrong_audience_issuer_expiry_or_member_is_401(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    liff = build_liff(tmp_path)
    liff.login.claims_by_token["odd"] = claims_of(MEMBER, liff.clock, **changes)
    assert liff.show(token="odd").status_code == 401
    assert liff.vote(0, token="odd").status_code == 401
    assert liff.polls.get(GROUP, liff.poll.id).options[0].voters == []


def test_a_token_that_runs_out_between_verify_and_the_check_is_401(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.login.claims_by_token["short"] = claims_of(
        MEMBER, liff.clock, exp=liff.clock().timestamp() + 1
    )
    assert liff.show(token="short").status_code == 200
    liff.clock.advance(seconds=2)
    assert liff.show(token="short").status_code == 401


@pytest.mark.parametrize("status", [0, 500, 502])
def test_when_line_cannot_verify_it_is_503_not_a_refusal_of_the_member(
    tmp_path: Path, status: int
) -> None:
    liff = build_liff(tmp_path)
    liff.login.error_status = status
    response = liff.show()
    assert response.status_code == 503
    assert response.json() == {"error": "unavailable"}


def test_someone_outside_the_group_is_403(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.login.claims_by_token["outsider"] = claims_of(OUTSIDER, liff.clock)
    assert liff.show(token="outsider").status_code == 403
    assert liff.vote(0, token="outsider").status_code == 403
    assert liff.polls.get(GROUP, liff.poll.id).options[0].voters == []


def test_an_unknown_poll_looks_the_same_as_a_poll_of_another_group(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    other = liff.polls.create("Cother", "Secret?", ["A", "B"])
    liff.login.claims_by_token["outsider"] = claims_of(OUTSIDER, liff.clock)
    unknown = liff.show(link_id="A" * 22)
    exists_but_not_yours = liff.show(link_id=other.link_id)
    not_a_member = liff.show(token="outsider")
    for response in (unknown, exists_but_not_yours, not_a_member):
        assert response.status_code == 403
        assert response.json() == {"error": "forbidden"}


@pytest.mark.parametrize("link_id", ["", "short", "../../etc/passwd", "a b" * 8, "A" * 200])
def test_a_link_id_of_the_wrong_shape_is_403(tmp_path: Path, link_id: str) -> None:
    assert build_liff(tmp_path).show(link_id=link_id).status_code == 403


def test_a_poll_of_a_group_that_is_not_allowed_is_403(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, allowed_groups=frozenset())
    assert liff.show().status_code == 403
    assert liff.vote(0).status_code == 403


def test_when_line_does_not_say_whether_the_member_is_in_the_group_it_is_503(
    tmp_path: Path,
) -> None:
    liff = build_liff(tmp_path)
    liff.line.members[MEMBER] = None
    assert liff.show().status_code == 503
    liff.line.members[MEMBER] = True
    assert liff.show().status_code == 200


def test_group_membership_is_remembered_for_five_minutes(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    assert liff.show().status_code == 200
    liff.line.members[MEMBER] = False
    liff.advance(299)
    assert liff.show().status_code == 200
    liff.advance(2)
    assert liff.show().status_code == 403


@pytest.mark.parametrize("call", ["show", "vote"])
def test_every_answer_says_no_store_even_a_refusal(tmp_path: Path, call: str) -> None:
    liff = build_liff(tmp_path)
    send = liff.show if call == "show" else lambda token: liff.vote(0, token)
    for token in (GOOD_TOKEN, "forged", None):
        assert send(token).headers["cache-control"] == "no-store"


def test_a_member_over_the_limit_is_429_and_others_are_not(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_per_minute=3)
    assert [liff.show().status_code for _ in range(4)] == [200, 200, 200, 429]
    assert liff.show(token=OTHER_TOKEN).status_code == 200
    liff.advance(61)
    assert liff.show().status_code == 200


def test_a_body_over_the_limit_is_413(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_body_bytes=200)
    big = json.dumps({"p": liff.poll.link_id, "filler": "x" * 500}).encode()
    response = liff.post("/liff/api/poll", big)
    assert response.status_code == 413
    assert response.json() == {"error": "too_large"}


@pytest.mark.parametrize("body", [b"", b"not json", b"[1]", b'{"option": 0}', b'{"p": 5}'])
def test_a_body_that_is_not_a_poll_request_is_400(tmp_path: Path, body: bytes) -> None:
    liff = build_liff(tmp_path)
    assert liff.post("/liff/api/poll", body).status_code == 400


@pytest.mark.parametrize("option", [-1, 2, 99, "0", None, True, 1.5])
def test_an_option_that_does_not_exist_is_400(tmp_path: Path, option: object) -> None:
    liff = build_liff(tmp_path)
    assert liff.vote(option).status_code == 400
    assert liff.polls.get(GROUP, liff.poll.id).options[0].voters == []


def test_a_vote_is_counted_under_the_members_profile_name(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    response = liff.vote(0)
    assert response.status_code == 200
    assert response.json()["options"][0] == {
        "label": "Kyoto",
        "count": 1,
        "voters": ["Aki"],
        "mine": True,
    }
    [voter] = liff.polls.get(GROUP, liff.poll.id).options[0].voters
    assert (voter.user_id, voter.name) == (MEMBER, "Aki")


def test_in_a_one_pick_poll_a_vote_moves_and_the_same_option_changes_nothing(
    tmp_path: Path,
) -> None:
    liff = build_liff(tmp_path)
    liff.vote(0)
    moved = liff.vote(1).json()
    assert [o["count"] for o in moved["options"]] == [0, 1]
    assert [o["mine"] for o in moved["options"]] == [False, True]
    again = liff.vote(1).json()
    assert [o["count"] for o in again["options"]] == [0, 1]
    assert again["voter_count"] == 1


def test_in_a_poll_with_several_picks_a_press_switches_the_option(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, multiple=True)
    liff.vote(0)
    both = liff.vote(1).json()
    assert [o["mine"] for o in both["options"]] == [True, True]
    assert both["voter_count"] == 1
    off = liff.vote(0).json()
    assert [o["mine"] for o in off["options"]] == [False, True]
    assert [o["count"] for o in off["options"]] == [0, 1]


def test_a_closed_poll_is_shown_but_takes_no_vote(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    liff.vote(0)
    liff.polls.close(GROUP, liff.poll.id)
    response = liff.vote(1)
    assert response.status_code == 200
    view = response.json()
    assert view["is_closed"] is True
    assert [o["count"] for o in view["options"]] == [1, 0]
    assert liff.show().json()["is_closed"] is True


def test_votes_from_the_page_and_from_the_card_land_in_the_same_poll(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    PostbackHandler(liff.polls).handle(
        GROUP,
        data=f"poll:{liff.poll.id}:0",
        user_id=OTHER_MEMBER,
        display_name="Ben",
        event_id="e1",
    )
    view = liff.vote(0).json()
    assert view["options"][0]["voters"] == ["Ben", "Aki"] and view["voter_count"] == 2
    pressed_again = PostbackHandler(liff.polls).handle(
        GROUP, data=f"poll:{liff.poll.id}:1", user_id=MEMBER, display_name="Aki", event_id="e2"
    )
    assert pressed_again is None
    assert [o["mine"] for o in liff.show().json()["options"]] == [False, True]


def test_an_old_poll_without_a_link_id_cannot_be_opened(tmp_path: Path) -> None:
    liff = build_liff(tmp_path)
    path = tmp_path / "groups" / GROUP / "polls.json"
    document = json.loads(path.read_text())
    del document["polls"][0]["link_id"]
    path.write_text(json.dumps(document))
    assert liff.show().status_code == 403
    assert liff.show(link_id="").status_code == 403


def test_logs_hold_neither_the_token_nor_the_link_nor_names(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    liff = build_liff(tmp_path)
    liff.login.claims_by_token["forged"] = claims_of(MEMBER, liff.clock, aud="9")
    with caplog.at_level(logging.DEBUG):
        liff.show()
        liff.vote(0)
        liff.show(token="forged")
        liff.login.error_status = 500
        liff.show()
    for secret in (GOOD_TOKEN, "forged", liff.poll.link_id, "Aki", "Which?", MEMBER, ISSUER):
        assert secret not in caplog.text
    assert "liff: a vote was counted" in caplog.text


def test_a_failed_verify_log_names_the_status_only(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    liff = build_liff(tmp_path)
    liff.login.error_status = 502
    with caplog.at_level(logging.INFO):
        liff.show()
    assert "status 502" in caplog.text
