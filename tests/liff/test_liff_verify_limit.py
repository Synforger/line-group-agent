import logging
from pathlib import Path

import pytest

from tests.liff.liff_harness import GOOD_TOKEN, OTHER_TOKEN, build_liff, claims_of

BAD_TOKEN = "made-up-token"


def test_over_the_limit_for_all_the_answer_is_429_and_line_is_not_asked(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=3)
    assert [liff.show(BAD_TOKEN).status_code for _ in range(3)] == [401, 401, 401]
    asked = len(liff.login.calls)
    for token in (BAD_TOKEN, "another-made-up-token", GOOD_TOKEN):
        response = liff.show(token)
        assert response.status_code == 429
        assert response.json() == {"error": "too_many_requests"}
    assert len(liff.login.calls) == asked


def test_a_source_over_its_limit_is_429_while_another_source_still_gets_through(
    tmp_path: Path,
) -> None:
    liff = build_liff(tmp_path, max_failed_verifies_per_source=2)
    assert [liff.show(BAD_TOKEN, forwarded_for="1.1.1.1").status_code for _ in range(2)] == [
        401,
        401,
    ]
    asked = len(liff.login.calls)
    assert liff.show(GOOD_TOKEN, forwarded_for="1.1.1.1").status_code == 429
    assert len(liff.login.calls) == asked
    assert liff.show(GOOD_TOKEN, forwarded_for="2.2.2.2").status_code == 200


def test_only_the_last_address_of_x_forwarded_for_names_the_source(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies_per_source=1)
    assert liff.show(BAD_TOKEN, forwarded_for="1.1.1.1, 9.9.9.9").status_code == 401
    assert liff.show(GOOD_TOKEN, forwarded_for="8.8.8.8, 9.9.9.9").status_code == 429
    assert liff.show(GOOD_TOKEN, forwarded_for="1.1.1.1").status_code == 200


def test_without_x_forwarded_for_only_the_limit_for_all_applies(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=12, max_failed_verifies_per_source=1)
    assert {liff.show(BAD_TOKEN).status_code for _ in range(12)} == {401}
    assert liff.show(GOOD_TOKEN).status_code == 429


@pytest.mark.parametrize("header", ["", "1.1.1.1, ", "x" * 65])
def test_an_empty_or_too_long_last_address_is_no_source(tmp_path: Path, header: str) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=12, max_failed_verifies_per_source=1)
    assert {liff.show(BAD_TOKEN, forwarded_for=header).status_code for _ in range(3)} == {401}


def test_the_limit_goes_away_when_the_failures_are_a_minute_old(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=2)
    liff.show(BAD_TOKEN)
    liff.show(BAD_TOKEN)
    assert liff.show(GOOD_TOKEN).status_code == 429
    liff.advance(60)
    assert liff.show(GOOD_TOKEN).status_code == 200


def test_good_tokens_are_not_counted(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=1, max_failed_verifies_per_source=1)
    for _ in range(5):
        assert liff.show(GOOD_TOKEN, forwarded_for="1.1.1.1").status_code == 200
        assert liff.show(OTHER_TOKEN, forwarded_for="1.1.1.1").status_code == 200


def test_a_token_that_line_accepts_but_the_claims_refuse_counts_as_a_failure(
    tmp_path: Path,
) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=1)
    liff.login.claims_by_token["wrong-aud"] = claims_of("Ux", liff.clock, aud="other")
    assert liff.show("wrong-aud").status_code == 401
    assert liff.show(GOOD_TOKEN).status_code == 429


def test_a_line_outage_is_not_counted_as_a_failed_token(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=1)
    liff.login.error_status = 503
    assert [liff.show().status_code for _ in range(3)] == [503, 503, 503]
    liff.login.error_status = None
    assert liff.show().status_code == 200


def test_a_request_without_a_token_is_not_a_failed_verify(tmp_path: Path) -> None:
    liff = build_liff(tmp_path, max_failed_verifies=1)
    assert [liff.show(None).status_code for _ in range(3)] == [401, 401, 401]
    assert liff.show(GOOD_TOKEN).status_code == 200


def test_the_log_says_which_limit_was_hit_and_holds_no_address(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    liff = build_liff(tmp_path, max_failed_verifies_per_source=1)
    liff.show(BAD_TOKEN, forwarded_for="203.0.113.7")
    with caplog.at_level(logging.INFO):
        liff.show(GOOD_TOKEN, forwarded_for="203.0.113.7")
    assert "too many failed verifies (source limit)" in caplog.text
    assert "203.0.113.7" not in caplog.text
