import pytest

from line_group_agent.itinerary.item_input import (
    ItemInputError,
    day_of,
    start_date_of,
    text_of,
    time_of,
    url_of,
)


def test_a_day_is_a_whole_number_from_one_to_thirty() -> None:
    assert [day_of(n) for n in (1, 30)] == [1, 30]
    for bad in (0, 31, -1, 1.5, "2", True, None):
        with pytest.raises(ItemInputError):
            day_of(bad)


def test_a_time_is_a_24_hour_time_and_an_hour_of_one_digit_is_padded() -> None:
    assert [time_of(raw, "start") for raw in ("09:30", "9:30", " 23:59 ", "00:00")] == [
        "09:30",
        "09:30",
        "23:59",
        "00:00",
    ]
    assert time_of(None, "start") is None and time_of("", "start") is None
    for bad in ("24:00", "9:60", "9", "9:5", "午前9時", 930, "09:30:00"):
        with pytest.raises(ItemInputError, match="start"):
            time_of(bad, "start")


def test_a_text_becomes_one_line_and_an_empty_one_is_nothing() -> None:
    assert text_of("  a \n b\t", "note", 20) == "a b"
    assert text_of("", "note", 20) is None and text_of(None, "note", 20) is None
    assert text_of("   ", "note", 20) is None


def test_a_required_text_may_not_be_empty() -> None:
    for empty in ("", None, "   "):
        with pytest.raises(ItemInputError, match="title is required"):
            text_of(empty, "title", 20, is_required=True)


def test_a_text_over_its_limit_is_refused_not_cut() -> None:
    assert text_of("x" * 20, "note", 20) == "x" * 20
    with pytest.raises(ItemInputError, match="over 20"):
        text_of("x" * 21, "note", 20)
    with pytest.raises(ItemInputError, match="must be text"):
        text_of(5, "note", 20)


def test_a_url_must_be_an_http_or_https_address_without_spaces() -> None:
    assert url_of("https://example.com/a?b=1") == "https://example.com/a?b=1"
    assert url_of("http://example.com") == "http://example.com"
    assert url_of("") is None and url_of(None) is None
    for bad in ("javascript:alert(1)", "data:text/html,x", "example.com", "https://a b", 3):
        with pytest.raises(ItemInputError):
            url_of(bad)
    with pytest.raises(ItemInputError, match="500"):
        url_of("https://example.com/" + "a" * 500)


def test_a_start_date_is_a_real_iso_date() -> None:
    assert start_date_of("2026-11-23") == "2026-11-23"
    assert start_date_of("") is None and start_date_of(None) is None
    for bad in ("2026-13-01", "2026-02-30", "20261123", "11/23", "2026-W47-1", 20261123):
        with pytest.raises(ItemInputError):
            start_date_of(bad)
