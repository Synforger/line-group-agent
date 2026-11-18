from typing import Any

from line_group_agent._common.one_line import cut_with_ellipsis
from line_group_agent.cards.card import (
    MAX_CARD_COUNT,
    PRICE_MAX_CHARS,
    TEXT_MAX_CHARS,
    TITLE_MAX_CHARS,
    URL_MAX_CHARS,
    Card,
)
from line_group_agent.cards.card_input import parse_cards


def card_input(**overrides: Any) -> dict[str, Any]:
    card = {"title": "Gion Inn", "text": "Near the station", "url": "https://example.com/gion"}
    card.update(overrides)
    return card


def parse_one(**overrides: Any) -> Card | None:
    cards = parse_cards({"cards": [card_input(**overrides)]})
    return cards[0] if cards else None


def test_a_full_card_is_read_field_by_field() -> None:
    card = parse_one(image_url="https://example.com/gion.jpg", price="¥2,980〜")
    assert card == Card(
        title="Gion Inn",
        text="Near the station",
        url="https://example.com/gion",
        image_url="https://example.com/gion.jpg",
        price="¥2,980〜",
    )


def test_image_and_price_are_optional() -> None:
    card = parse_one()
    assert card is not None and card.image_url is None and card.price is None


def test_a_url_that_is_not_https_drops_the_card() -> None:
    for url in ["http://example.com", "javascript:alert(1)", "line://nv/camera", "example.com", ""]:
        assert parse_one(url=url) is None


def test_a_url_with_a_space_or_control_character_drops_the_card() -> None:
    for url in [
        "https://example.com/a b",
        "https://example.com/a\nb",
        "https://example.com/a\x00b",
        "https://example.com/a　b",
        "https://example.com/a\x7fb",
    ]:
        assert parse_one(url=url) is None


def test_a_url_without_a_host_drops_the_card() -> None:
    assert parse_one(url="https://") is None
    assert parse_one(url="https:///path") is None


def test_a_url_over_the_limit_drops_the_card_and_one_at_the_limit_stays() -> None:
    prefix = "https://example.com/"
    assert parse_one(url=prefix + "a" * (URL_MAX_CHARS - len(prefix))) is not None
    assert parse_one(url=prefix + "a" * (URL_MAX_CHARS - len(prefix) + 1)) is None


def test_the_url_around_it_is_trimmed_but_not_inside() -> None:
    card = parse_one(url="  https://example.com/x \n")
    assert card is not None and card.url == "https://example.com/x"


def test_non_ascii_in_a_url_is_percent_encoded_before_the_length_is_checked() -> None:
    card = parse_one(url="https://example.com/京都")
    assert card is not None and card.url == "https://example.com/%E4%BA%AC%E9%83%BD"
    long_japanese = "https://example.com/" + "京" * 200
    assert parse_one(url=long_japanese) is None


def test_a_bad_image_url_removes_only_the_image() -> None:
    for image_url in ["http://example.com/a.jpg", "https://example.com/a b.jpg", "", 5]:
        card = parse_one(image_url=image_url)
        assert card is not None and card.image_url is None and card.title == "Gion Inn"


def test_long_text_is_cut_with_an_ellipsis_at_each_limit() -> None:
    card = parse_one(title="t" * 100, text="x" * 100, price="p" * 100)
    assert card is not None
    assert card.title == "t" * (TITLE_MAX_CHARS - 1) + "…"
    assert card.text == "x" * (TEXT_MAX_CHARS - 1) + "…"
    assert card.price == "p" * (PRICE_MAX_CHARS - 1) + "…"


def test_text_at_the_limit_is_kept_whole() -> None:
    card = parse_one(title="t" * TITLE_MAX_CHARS, text="x" * TEXT_MAX_CHARS)
    assert card is not None
    assert card.title == "t" * TITLE_MAX_CHARS and card.text == "x" * TEXT_MAX_CHARS


def test_line_breaks_and_control_characters_become_one_line() -> None:
    card = parse_one(title="Gion\n Inn\x00", text="a\r\n\tb")
    assert card is not None and card.title == "Gion Inn" and card.text == "a b"


def test_a_card_without_a_title_is_dropped_but_a_missing_text_is_empty() -> None:
    assert parse_one(title="  ") is None
    assert parse_one(title=None) is None
    card = parse_one(text=None)
    assert card is not None and card.text == ""


def test_at_most_ten_cards_are_kept_in_order() -> None:
    raw = {"cards": [card_input(title=f"hotel {n}") for n in range(15)]}
    cards = parse_cards(raw)
    assert len(cards) == MAX_CARD_COUNT == 10
    assert [c.title for c in cards] == [f"hotel {n}" for n in range(10)]


def test_dropped_cards_do_not_use_up_the_ten() -> None:
    raw = {"cards": [card_input(url="http://bad")] * 5 + [card_input()] * 10}
    assert len(parse_cards(raw)) == 10


def test_something_that_is_not_a_card_list_gives_no_cards() -> None:
    for raw in [None, "x", [], {}, {"cards": "x"}, {"cards": [1, None, "x"]}]:
        assert parse_cards(raw) == []


def test_cut_with_ellipsis_counts_the_ellipsis_in_the_limit() -> None:
    assert cut_with_ellipsis("abc", 3) == "abc"
    assert cut_with_ellipsis("abcd", 3) == "ab…"
