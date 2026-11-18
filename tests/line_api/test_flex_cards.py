import json
from typing import Any

from line_group_agent.cards.card import MAX_CARD_COUNT, URL_MAX_CHARS, Card
from line_group_agent.line_api.flex_cards import ALT_TEXT_MAX_CHARS, alt_text_of, build_flex_message

# What LINE's reference lists as required for each element used here.
REQUIRED = {
    "bubble": {"type"},
    "box": {"type", "layout", "contents"},
    "text": {"type"},
    "button": {"type", "action"},
    "image": {"type", "url"},
    "carousel": {"type", "contents"},
}
URI_ACTION_REQUIRED = {"type", "uri"}
CAROUSEL_MAX_BUBBLES = 12
CAROUSEL_MAX_BYTES = 50 * 1024
BUBBLE_MAX_BYTES = 30 * 1024


def full_card(number: int = 1) -> Card:
    return Card(
        title=f"Hotel {number}",
        text="A quiet room by the river",
        url=f"https://example.com/{number}",
        image_url=f"https://example.com/{number}.jpg",
        price="¥2,980〜",
    )


def walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        found.append(node)
        for value in node.values():
            found.extend(walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk(item))
    return found


def test_the_message_has_the_fields_a_flex_message_needs() -> None:
    message = build_flex_message([full_card(1), full_card(2)])
    assert message["type"] == "flex"
    assert isinstance(message["altText"], str) and message["altText"]
    assert message["contents"]["type"] == "carousel"
    assert len(message["contents"]["contents"]) == 2


def test_every_element_carries_its_required_fields() -> None:
    message = build_flex_message([full_card(n) for n in range(3)])
    for element in walk(message["contents"]):
        kind = element.get("type")
        if kind in REQUIRED:
            assert REQUIRED[kind] <= element.keys(), kind
        if kind == "uri":
            assert URI_ACTION_REQUIRED <= element.keys()
        if kind == "box":
            assert element["layout"] in {"horizontal", "vertical", "baseline"}


def test_a_bubble_shows_the_image_then_title_price_text_and_an_open_button() -> None:
    [bubble] = build_flex_message([full_card()])["contents"]["contents"]
    assert bubble["hero"] == {
        "type": "image",
        "url": "https://example.com/1.jpg",
        "size": "full",
        "aspectRatio": "20:13",
        "aspectMode": "cover",
        "action": {"type": "uri", "uri": "https://example.com/1"},
    }
    title, price, text = bubble["body"]["contents"]
    assert title["text"] == "Hotel 1" and title["weight"] == "bold" and title["wrap"] is True
    assert price["text"] == "¥2,980〜"
    assert text["text"] == "A quiet room by the river" and text["wrap"] is True
    [button] = bubble["footer"]["contents"]
    assert button["type"] == "button"
    assert button["action"] == {"type": "uri", "label": "開く", "uri": "https://example.com/1"}


def test_a_card_without_an_image_has_no_hero_and_without_price_no_price_line() -> None:
    card = Card("Hotel", "text", "https://example.com/1")
    [bubble] = build_flex_message([card])["contents"]["contents"]
    assert "hero" not in bubble
    assert [c["text"] for c in bubble["body"]["contents"]] == ["Hotel", "text"]


def test_without_images_no_bubble_has_a_hero() -> None:
    message = build_flex_message([full_card(1), full_card(2)], with_images=False)
    assert all("hero" not in b for b in message["contents"]["contents"])
    assert "image" not in {e.get("type") for e in walk(message)}


def test_every_bubble_is_the_same_size_so_the_carousel_is_valid() -> None:
    bubbles = build_flex_message([full_card(1), Card("b", "", "https://e.com")])["contents"][
        "contents"
    ]
    assert len({b.get("size") for b in bubbles}) == 1


def test_the_alt_text_lists_the_names() -> None:
    assert alt_text_of([full_card(1), full_card(2)]) == "候補: Hotel 1 / Hotel 2"


def test_the_alt_text_is_cut_to_400_characters() -> None:
    cards = [Card("t" * 40, "", "https://e.com") for _ in range(10)]
    alt = alt_text_of(cards)
    assert len(alt) == ALT_TEXT_MAX_CHARS == 400
    assert alt.endswith("…")


def test_the_largest_possible_carousel_is_inside_lines_size_limits() -> None:
    url = "https://example.com/" + "a" * (URL_MAX_CHARS - len("https://example.com/"))
    big = Card("題" * 40, "文" * 60, url, image_url=url, price="価" * 20)
    message = build_flex_message([big] * MAX_CARD_COUNT)
    assert MAX_CARD_COUNT <= CAROUSEL_MAX_BUBBLES
    assert len(json.dumps(message, ensure_ascii=False).encode()) < CAROUSEL_MAX_BYTES
    one_bubble = json.dumps(message["contents"]["contents"][0], ensure_ascii=False)
    assert len(one_bubble.encode()) < BUBBLE_MAX_BYTES
