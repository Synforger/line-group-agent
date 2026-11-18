from line_group_agent.agent.plain_text import to_plain_card, to_plain_text
from line_group_agent.cards.card import Card


def test_heading_marks_at_the_start_of_a_line_are_removed() -> None:
    assert to_plain_text("# Plan\n## Day 1\ntext") == "Plan\nDay 1\ntext"


def test_bold_marks_are_removed_and_the_words_stay() -> None:
    assert to_plain_text("Try **Gion Inn** first") == "Try Gion Inn first"


def test_dash_and_star_bullets_become_middle_dots_and_keep_their_indent() -> None:
    assert to_plain_text("- one\n* two\n  - three") == "・one\n・two\n  ・three"


def test_a_hash_or_dash_inside_a_line_stays() -> None:
    text = "Room #5 costs 5-6k, a - b"
    assert to_plain_text(text) == text


def test_numbers_and_middle_dots_are_left_as_they_are() -> None:
    text = "1. Gion\n2. Arashiyama\n・Kiyomizu"
    assert to_plain_text(text) == text


def test_every_text_field_of_a_card_is_made_plain_and_urls_stay() -> None:
    card = Card(
        "**Gion Inn**",
        "- near the station",
        "https://example.com/a",
        "https://e.com/a.jpg",
        "**¥2,980**",
    )
    plain = to_plain_card(card)
    assert (plain.title, plain.text, plain.price) == ("Gion Inn", "・near the station", "¥2,980")
    assert (plain.url, plain.image_url) == ("https://example.com/a", "https://e.com/a.jpg")


def test_a_card_without_a_price_stays_without_one() -> None:
    assert to_plain_card(Card("A", "b", "https://example.com")).price is None
