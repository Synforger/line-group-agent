import logging
from pathlib import Path

import pytest

from tests.liff.itinerary_harness import build_itinerary_liff
from tests.liff.liff_harness import GOOD_TOKEN, ISSUER, LIFF_ID, MEMBER, claims_of
from tests.world import GROUP

LONG_AGO = -7200


def test_the_page_is_served_with_the_liff_id_and_no_group_content(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    page = liff.client.get("/liff/itinerary")
    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert f'"{LIFF_ID}"' in page.text
    for content in ("Kyoto trip", "Kiyomizu", "Lunch", GROUP, MEMBER, liff.link_id):
        assert content not in page.text


def test_the_page_may_not_be_cached_or_leak_its_address(tmp_path: Path) -> None:
    headers = build_itinerary_liff(tmp_path).client.get("/liff/itinerary").headers
    assert headers["cache-control"] == "no-store"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"


def test_the_voting_page_is_still_where_it_was(tmp_path: Path) -> None:
    assert build_itinerary_liff(tmp_path).client.get("/liff/").status_code == 200


def test_a_member_gets_the_plan_of_their_group(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    response = liff.show()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    view = response.json()
    assert view["title"] == "Kyoto trip" and view["start_date"] == "2026-11-23"
    assert [d["label"] for d in view["days"]] == ["11/23(月) 1日目", "11/24(火) 2日目"]
    first_day = view["days"][0]
    assert [i["title"] for i in first_day["scheduled"]] == ["Kiyomizu", "Lunch"]
    assert [i["title"] for i in view["days"][1]["unscheduled"]] == ["Free day"]


def test_the_answer_holds_no_id_of_a_group_a_member_or_an_item(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    ids = [item.id for item in liff.itineraries.get(GROUP).items]  # type: ignore[union-attr]
    text = liff.show().text
    for secret in (GROUP, MEMBER, liff.link_id, *ids):
        assert secret not in text


def test_the_link_of_another_group_gives_nothing_of_theirs(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    response = liff.show(link_id=liff.other_link_id)
    assert response.status_code == 403
    assert response.json() == {"error": "forbidden"}
    assert "Secret" not in response.text


def test_an_unknown_or_malformed_link_is_refused_without_a_hint(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    known = liff.show(link_id="x" * 22)
    for guess in ("", "short", "../" * 8, "x" * 100):
        assert liff.show(link_id=guess).status_code == 403
    assert known.json() == {"error": "forbidden"}


def test_a_link_of_a_group_that_is_not_allowed_is_refused(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path, allowed_groups=frozenset({"Cother"}))
    assert liff.show().status_code == 403


def test_a_missing_or_bad_token_is_refused_with_401(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    assert liff.show(token=None).status_code == 401
    assert liff.show(token="not-a-token").status_code == 401
    assert liff.show(token="x" * 5000).status_code == 401


@pytest.mark.parametrize(
    "changes",
    [{"aud": "someone-else"}, {"iss": "https://evil.example"}, {"exp": LONG_AGO}, {"sub": ""}],
)
def test_a_token_made_for_another_channel_or_expired_is_refused(
    tmp_path: Path, changes: dict[str, object]
) -> None:
    liff = build_itinerary_liff(tmp_path)
    liff.login.claims_by_token["bad"] = claims_of(MEMBER, liff.clock, **changes)
    assert liff.show(token="bad").status_code == 401
    assert ISSUER not in liff.show(token="bad").text


def test_a_member_of_no_such_group_is_refused_with_403(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    liff.line.members_by_group[GROUP] = set()
    assert liff.show().status_code == 403


def test_when_line_does_not_say_whether_they_are_a_member_the_answer_is_503(
    tmp_path: Path,
) -> None:
    liff = build_itinerary_liff(tmp_path)
    liff.line.is_unclear = True
    assert liff.show().status_code == 503


def test_a_body_that_is_not_an_object_or_has_no_link_is_a_bad_request(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    headers = {"Authorization": f"Bearer {GOOD_TOKEN}"}
    for body in (b"[1]", b"not json", b'{"i": 5}', b"{}", b'{"p": "x"}'):
        assert (
            liff.client.post("/liff/api/itinerary", content=body, headers=headers).status_code
            == 400
        )
    too_big = liff.client.post("/liff/api/itinerary", content=b" " * 2000, headers=headers)
    assert too_big.status_code == 413


def test_the_answer_is_only_given_to_a_post(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    assert liff.client.get("/liff/api/itinerary").status_code == 405
    assert liff.client.get(f"/liff/api/itinerary?i={liff.link_id}").status_code == 405


def test_a_member_over_the_request_limit_gets_429(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path, max_per_minute=2)
    assert [liff.show().status_code for _ in range(3)] == [200, 200, 429]


def test_the_plan_is_read_again_after_it_changes(tmp_path: Path) -> None:
    liff = build_itinerary_liff(tmp_path)
    liff.itineraries.add_item(GROUP, day=2, title="Added later", start="08:00")
    titles = [i["title"] for i in liff.show().json()["days"][1]["scheduled"]]
    assert titles == ["Added later"]


def test_a_refusal_is_logged_without_the_token_or_the_link(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    liff = build_itinerary_liff(tmp_path)
    with caplog.at_level(logging.INFO):
        liff.show(link_id=liff.other_link_id)
        liff.show(token="not-a-token")
    for secret in (GOOD_TOKEN, "not-a-token", liff.other_link_id, liff.link_id):
        assert secret not in caplog.text
