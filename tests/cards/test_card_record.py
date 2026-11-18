from line_group_agent.cards.card import Card
from line_group_agent.cards.card_record import format_card_record


def test_the_record_numbers_each_card_with_name_price_and_address() -> None:
    cards = [
        Card("Gion Inn", "x", "https://example.com/1", price="¥2,980〜"),
        Card("River Hotel", "y", "https://example.com/2"),
    ]
    assert format_card_record(cards) == (
        "[カード] 1. Gion Inn (¥2,980〜) https://example.com/1 / 2. River Hotel https://example.com/2"
    )
