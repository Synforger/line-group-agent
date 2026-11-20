from line_group_agent.cards.card import Card
from line_group_agent.line_api.flex_cards import build_flex_message
from line_group_agent.simulator.flex_html import FlexHtml
from line_group_agent.simulator.message_actions import action_numbers

CARDS = [
    Card(
        "Kiyomizu-dera",
        "Old temple on a hill",
        "https://example.com/k",
        "https://example.com/k.jpg",
        "¥400",
    ),
    Card("Fushimi Inari", "Gates", "https://example.com/f"),
]


def draw(message: dict) -> str:
    return FlexHtml(action_numbers([message])).render(message["contents"])


def test_a_carousel_has_a_bubble_per_card_with_its_text_image_and_button() -> None:
    html = draw(build_flex_message(CARDS))
    assert html.count('class="fx-bubble"') == 2
    assert 'class="fx-carousel"' in html
    assert "Kiyomizu-dera" in html and "¥400" in html and "Old temple on a hill" in html
    assert html.count("<img") == 1 and "https://example.com/k.jpg" in html
    assert html.count("開く") == 2


def test_the_buttons_carry_their_numbers_in_the_order_a_scenario_names_them() -> None:
    html = draw(build_flex_message(CARDS))
    # card 1: the hero's link, then its button; card 2: its button.
    assert html.index("#0") < html.index("#1") < html.index("#2")


def test_a_poll_card_with_postback_buttons_shows_each_option() -> None:
    message = {
        "type": "flex",
        "altText": "poll",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "Where?", "weight": "bold", "wrap": True},
                    {
                        "type": "button",
                        "style": "secondary",
                        "action": {"type": "postback", "label": "Kyoto", "data": "poll:p1:0"},
                    },
                ],
            },
        },
    }
    html = draw(message)
    assert "Where?" in html and "font-weight:700" in html
    assert 'class="fx-button fx-secondary"' in html and "Kyoto" in html


def test_text_from_the_bot_is_escaped() -> None:
    message = {
        "type": "flex",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "text", "text": "<script>alert(1)</script>", "color": "red;x"}
                ],
            },
        },
    }
    html = draw(message)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "color:red" not in html


def test_something_that_is_not_flex_is_marked_not_dropped() -> None:
    assert "[flex]" in FlexHtml({}).render(None)
    assert "[mystery]" in FlexHtml({}).render({"type": "bubble", "body": {"type": "mystery"}})
