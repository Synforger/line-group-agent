from line_group_agent._common.one_line import cut_with_ellipsis, one_line


def test_a_text_within_the_limit_is_kept() -> None:
    assert cut_with_ellipsis("abc", 3) == "abc"


def test_a_longer_text_ends_in_an_ellipsis_that_counts_in_the_limit() -> None:
    assert cut_with_ellipsis("abcd", 3) == "ab…"


def test_one_line_joins_lines_drops_control_characters_and_cuts() -> None:
    assert one_line("  two\nlines \x00here ", 40) == "two lines here"
    assert one_line("x" * 30, 10) == "x" * 9 + "…"


def test_anything_that_is_not_a_string_is_an_empty_line() -> None:
    assert one_line(None, 10) == "" and one_line(5, 10) == ""
