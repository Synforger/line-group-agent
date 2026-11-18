import pytest

from line_group_agent.cards.card_name_match import page_is_about


@pytest.mark.parametrize(
    ("card_title", "page_title"),
    [
        ("Gion Inn", "Gion Inn - Kyoto"),
        ("ホテルグランヴィア広島（ほてる）", "ホテルグランヴィア広島 公式"),
        ("ホテルグランヴィア広島（ほてる）", "ほてる"),
        ("【人気】カフェ・ド・ロペ", "カフェ・ド・ロペ | 食べログ"),
        ("【人気】カフェ・ド・ロペ", "人気"),
        ("ＧＩＯＮ　ＩＮＮ", "gion inn"),
        ("Gion  Inn", "the GION INN"),
    ],
)
def test_a_page_title_holding_the_name_or_a_bracketed_text_matches(
    card_title: str, page_title: str
) -> None:
    assert page_is_about(card_title, page_title)


@pytest.mark.parametrize(
    ("card_title", "page_title"),
    [
        ("カフェ・ド・ロペ", "広島のおすすめカフェ10選"),
        ("Gion Inn", None),
        ("Gion Inn", ""),
        ("Gion Inn", "Kyoto Inn"),
    ],
)
def test_a_page_title_without_the_name_does_not_match(
    card_title: str, page_title: str | None
) -> None:
    assert not page_is_about(card_title, page_title)


def test_a_name_of_one_character_is_not_used() -> None:
    assert not page_is_about("駅", "駅前のカフェ")
    assert not page_is_about("A", "A cafe")
    assert not page_is_about("（ほ）", "ほ")


def test_a_one_character_name_does_not_stop_a_longer_bracketed_one_from_matching() -> None:
    assert page_is_about("駅（えきまえ）", "えきまえ食堂")
