from line_group_agent.line_api.mention_text import (
    MAX_MENTIONS,
    build_text_v2,
    has_mention_marks,
    strip_mention_marks,
)

PEOPLE = {"Aki": "Uaki", "Ben": "Uben"}
LIMIT = 5000


def test_a_mark_with_a_known_name_becomes_a_mention() -> None:
    result = build_text_v2(
        "<mention>Aki</mention>さん、割り勘は1200円です", PEOPLE, limit_utf16_units=LIMIT
    )
    assert result is not None
    assert result.text == "{m1}さん、割り勘は1200円です"
    assert result.substitution == {
        "m1": {"type": "mention", "mentionee": {"type": "user", "userId": "Uaki"}}
    }


def test_each_mark_gets_its_own_placeholder() -> None:
    text = "<mention>Aki</mention> と <mention>Ben</mention> と <mention>Aki</mention>"
    result = build_text_v2(text, PEOPLE, limit_utf16_units=LIMIT)
    assert result is not None and result.text == "{m1} と {m2} と {m3}"
    assert result.substitution["m3"]["mentionee"]["userId"] == "Uaki"


def test_a_name_that_is_not_in_the_record_stays_as_plain_text() -> None:
    text = "<mention>Cleo</mention>さん、<mention>Aki</mention>さん"
    result = build_text_v2(text, PEOPLE, limit_utf16_units=LIMIT)
    assert result is not None and result.text == "Cleoさん、{m1}さん"
    assert list(result.substitution) == ["m1"]


def test_without_a_matching_name_there_is_no_text_v2() -> None:
    assert build_text_v2("<mention>Cleo</mention>", PEOPLE, limit_utf16_units=LIMIT) is None
    assert build_text_v2("no marks", PEOPLE, limit_utf16_units=LIMIT) is None


def test_the_name_must_match_exactly_but_spaces_around_it_are_ignored() -> None:
    assert build_text_v2("<mention>aki</mention>", PEOPLE, limit_utf16_units=LIMIT) is None
    result = build_text_v2("<mention> Aki </mention>", PEOPLE, limit_utf16_units=LIMIT)
    assert result is not None and result.text == "{m1}"


def test_everyone_is_never_mentioned() -> None:
    people = {"all": "Uall", "Aki": "Uaki"}
    result = build_text_v2(
        "<mention>all</mention> <mention>Aki</mention>", people, limit_utf16_units=LIMIT
    )
    assert result is not None and result.text == "all {m1}"


def test_literal_braces_are_doubled() -> None:
    result = build_text_v2("{x} <mention>Aki</mention> }", PEOPLE, limit_utf16_units=LIMIT)
    assert result is not None and result.text == "{{x}} {m1} }}"


def test_a_message_has_at_most_twenty_mentions() -> None:
    text = " ".join("<mention>Aki</mention>" for _ in range(MAX_MENTIONS + 2))
    result = build_text_v2(text, PEOPLE, limit_utf16_units=LIMIT)
    assert result is not None
    assert len(result.substitution) == MAX_MENTIONS
    assert result.text.endswith("Aki Aki")


def test_a_text_too_long_for_line_is_not_made_a_mention() -> None:
    text = "<mention>Aki</mention>" + "あ" * 20
    assert build_text_v2(text, PEOPLE, limit_utf16_units=10) is None


def test_a_stray_tag_is_dropped() -> None:
    result = build_text_v2(
        "<mention>Aki</mention> </mention> <mention>", PEOPLE, limit_utf16_units=LIMIT
    )
    assert result is not None and result.text == "{m1}  "


def test_marks_are_replaced_by_the_names() -> None:
    assert (
        strip_mention_marks("<mention>Aki</mention>さん、<mention> Ben </mention>")
        == "Akiさん、Ben"
    )
    assert strip_mention_marks("a </mention> b <mention>") == "a  b "
    assert strip_mention_marks("plain") == "plain"


def test_a_mark_is_found() -> None:
    assert has_mention_marks("x <mention>Aki</mention>")
    assert not has_mention_marks("x")
