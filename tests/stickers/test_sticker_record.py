from line_group_agent.stickers.sticker_record import received_sticker_line, sticker_line


def test_a_sticker_is_recorded_with_its_keywords() -> None:
    message = {"type": "sticker", "keywords": ["thanks", "ありがとう", "smile"]}
    assert received_sticker_line(message) == "(スタンプ: thanks、ありがとう、smile)"


def test_a_sticker_without_keywords_is_recorded_without_them() -> None:
    assert received_sticker_line({"type": "sticker"}) == "(スタンプ)"
    assert received_sticker_line({"type": "sticker", "keywords": []}) == "(スタンプ)"
    assert received_sticker_line({"type": "sticker", "keywords": [1, " ", None]}) == "(スタンプ)"


def test_keywords_are_kept_to_one_short_line() -> None:
    line = received_sticker_line({"keywords": ["a\nb", "x" * 500]})
    assert "\n" not in line and len(line) < 130 and line.startswith("(スタンプ: a b、")


def test_the_line_of_a_sent_sticker_shows_its_name() -> None:
    assert sticker_line("ありがとう") == "(スタンプ: ありがとう)"
