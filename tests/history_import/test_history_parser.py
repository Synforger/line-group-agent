from datetime import datetime

import pytest

from line_group_agent.history_import.history_parser import HistoryMessage, parse_history

SAMPLE = '''\
[LINE] Trip friends のトーク履歴
保存日時：2026/11/18 12:00

2026/11/17(火)
10:00\tAki\tおはよう
10:01\tSora\t"こんにちは
今日もよろしく"
10:02\tAki\t"He said ""hi"""
10:03\tAki\t[写真]
10:04\tSora\tメッセージの送信を取り消しました
10:05\tAki invited Sora.

2026/11/18(水)
09:00\tSora\tgood morning
'''


def message(day: int, hour: int, minute: int, name: str, text: str) -> HistoryMessage:
    return HistoryMessage(datetime(2026, 11, day, hour, minute), name, text)


def test_a_whole_file_is_read_message_by_message() -> None:
    parsed = parse_history(SAMPLE)
    assert parsed.messages == [
        message(17, 10, 0, "Aki", "おはよう"),
        message(17, 10, 1, "Sora", "こんにちは\n今日もよろしく"),
        message(17, 10, 2, "Aki", 'He said "hi"'),
        message(17, 10, 3, "Aki", "[写真]"),
        message(18, 9, 0, "Sora", "good morning"),
    ]
    assert (parsed.notice_count, parsed.unrecognized_count) == (2, 0)


def test_lines_with_windows_endings_are_read_the_same() -> None:
    assert parse_history(SAMPLE.replace("\n", "\r\n")) == parse_history(SAMPLE)


@pytest.mark.parametrize(
    "date_line",
    ["2026/11/17(火)", "2026/11/17", "2026.11.17 Tuesday", "2026-11-17", "Tue, 11/17/2026"],
)
def test_the_forms_a_date_line_takes(date_line: str) -> None:
    parsed = parse_history(f"{date_line}\n10:00\tAki\thi\n")
    assert parsed.messages == [message(17, 10, 0, "Aki", "hi")]


@pytest.mark.parametrize(
    ("clock", "expected"),
    [("9:05", (9, 5)), ("午後 3:07", (15, 7)), ("午前 12:30", (0, 30)),
     ("3:07 PM", (15, 7)), ("12:30 AM", (0, 30)), ("12:30 PM", (12, 30))],
)  # fmt: skip
def test_times_in_twelve_hour_forms(clock: str, expected: tuple[int, int]) -> None:
    parsed = parse_history(f"2026/11/17\n{clock}\tAki\thi\n")
    assert [(m.moment.hour, m.moment.minute) for m in parsed.messages] == [expected]


def test_a_line_of_a_shape_not_known_is_counted_and_the_rest_is_still_read() -> None:
    text = "2026/11/17\nsomething else\n10:00 no tab here\n10:00\tAki\thi\n25:00\tAki\tlate\n"
    parsed = parse_history(text)
    assert parsed.messages == [message(17, 10, 0, "Aki", "hi")]
    assert parsed.unrecognized_count == 3


def test_a_message_before_any_date_is_not_understood() -> None:
    parsed = parse_history("10:00\tAki\thi\n2026/11/17\n10:01\tAki\tyes\n")
    assert [m.text for m in parsed.messages] == ["yes"] and parsed.unrecognized_count == 1


def test_a_date_that_does_not_exist_is_not_understood() -> None:
    parsed = parse_history("2026/13/40\n10:00\tAki\thi\n")
    assert parsed.messages == [] and parsed.unrecognized_count == 2


def test_a_quoted_text_that_never_closes_is_taken_to_the_end_of_the_file() -> None:
    parsed = parse_history('2026/11/17\n10:00\tAki\t"open\nstill open\n')
    assert parsed.messages == [message(17, 10, 0, "Aki", "open\nstill open\n")]


def test_a_quoted_text_that_looks_like_a_message_inside_is_one_message() -> None:
    text = '2026/11/17\n10:00\tAki\t"line\n10:01\tSora\tnot a new message"\n10:02\tSora\tnext\n'
    parsed = parse_history(text)
    assert [m.text for m in parsed.messages] == ["line\n10:01\tSora\tnot a new message", "next"]


def test_a_text_with_a_tab_keeps_it() -> None:
    parsed = parse_history("2026/11/17\n10:00\tAki\ta\tb\n")
    assert parsed.messages[0].text == "a\tb"


def test_an_empty_quoted_text_and_an_empty_file() -> None:
    assert parse_history('2026/11/17\n10:00\tAki\t""\n').messages[0].text == ""
    empty = parse_history("")
    assert empty.messages == [] and (empty.notice_count, empty.unrecognized_count) == (0, 0)


def test_english_unsent_notices_are_skipped() -> None:
    parsed = parse_history("2026/11/17\n10:00\tAki\tAki unsent a message.\n")
    assert parsed.messages == [] and parsed.notice_count == 1
