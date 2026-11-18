from line_group_agent.polls.poll import KIND_DATE, Poll, PollOption, Voter
from line_group_agent.polls.poll_message import (
    CHOICE_HINT,
    DATE_HINT,
    DISPLAY_TEXT_MAX_CHARS,
    LIFF_BUTTON_LABEL,
    MULTIPLE_HINT,
    build_poll_message,
    liff_poll_url,
    postback_data_of,
)


def poll(kind: str = "choice", *, multiple: bool = False) -> Poll:
    return Poll(
        "p3", kind, "Where?", [PollOption("Kyoto"), PollOption("Osaka")], multiple, False, "t"
    )


def test_the_postback_data_holds_the_poll_and_the_option() -> None:
    assert postback_data_of("p3", 1) == "poll:p3:1"


def test_the_card_has_the_question_a_hint_and_a_postback_button_per_option() -> None:
    message = build_poll_message(poll())
    assert message["type"] == "flex"
    body = message["contents"]["body"]["contents"]
    assert body[0]["text"] == "Where?" and body[1]["text"] == CHOICE_HINT
    assert [b["action"] for b in body[2:]] == [
        {"type": "postback", "label": "Kyoto", "data": "poll:p3:0", "displayText": "Kyoto に投票"},
        {"type": "postback", "label": "Osaka", "data": "poll:p3:1", "displayText": "Osaka に投票"},
    ]


def test_a_poll_that_allows_several_picks_has_no_display_text() -> None:
    for chosen in (poll(multiple=True), poll(KIND_DATE, multiple=True)):
        buttons = build_poll_message(chosen)["contents"]["body"]["contents"][2:]
        assert all("displayText" not in b["action"] for b in buttons)


def test_the_display_text_keeps_the_whole_label_and_stays_under_lines_limit() -> None:
    long = Poll("p1", "choice", "Q", [PollOption("x" * 500), PollOption("y")], False, False, "t")
    action = build_poll_message(long)["contents"]["body"]["contents"][2]["action"]
    assert len(action["displayText"]) == DISPLAY_TEXT_MAX_CHARS
    assert action["displayText"].endswith("…")
    assert len(action["label"]) == 20


def test_the_hint_follows_the_kind_of_poll() -> None:
    hints = [
        build_poll_message(poll(multiple=True))["contents"]["body"]["contents"][1]["text"],
        build_poll_message(poll(KIND_DATE))["contents"]["body"]["contents"][1]["text"],
    ]
    assert hints == [MULTIPLE_HINT, DATE_HINT]


def test_a_long_option_label_is_cut_to_what_a_button_takes() -> None:
    long = Poll("p1", "choice", "Q", [PollOption("x" * 50), PollOption("y")], False, False, "t")
    label = build_poll_message(long)["contents"]["body"]["contents"][2]["action"]["label"]
    assert len(label) == 20 and label.endswith("…")


def test_the_alt_text_stands_in_for_the_card_in_notifications() -> None:
    assert build_poll_message(poll())["altText"] == f"{CHOICE_HINT}: Where?"


LINK = "L" * 22


def paged_poll(**changes: object) -> Poll:
    chosen = Poll(
        "p3",
        "choice",
        "Where?",
        [PollOption("Kyoto", [Voter("U1", "Aki"), Voter("U2", None)]), PollOption("Osaka")],
        False,
        False,
        "t",
        LINK,
    )
    for name, value in changes.items():
        setattr(chosen, name, value)
    return chosen


def test_the_link_of_a_poll_opens_the_liff_app_with_the_poll_id() -> None:
    assert (
        liff_poll_url("1234567890-AbCdEfGh", LINK)
        == f"https://liff.line.me/1234567890-AbCdEfGh?p={LINK}"
    )


def test_with_a_liff_app_the_card_lists_the_counts_and_has_one_button_to_the_page() -> None:
    message = build_poll_message(paged_poll(), liff_id="1234567890-AbCdEfGh")
    body = message["contents"]["body"]["contents"]
    assert body[0]["text"] == "Where?" and body[1]["text"] == CHOICE_HINT
    assert [entry["text"] for entry in body[2:4]] == ["1. Kyoto: 2票", "2. Osaka: 0票"]
    [button] = body[4:]
    assert button["type"] == "button"
    assert button["action"] == {
        "type": "uri",
        "label": LIFF_BUTTON_LABEL,
        "uri": f"https://liff.line.me/1234567890-AbCdEfGh?p={LINK}",
    }
    assert all(entry["type"] != "button" for entry in body[:4])


def test_with_a_liff_app_no_option_has_a_postback_or_a_display_text() -> None:
    message = build_poll_message(paged_poll(multiple=True), liff_id="1234567890-AbCdEfGh")
    actions = [
        entry["action"]
        for entry in message["contents"]["body"]["contents"]
        if entry["type"] == "button"
    ]
    assert [action["type"] for action in actions] == ["uri"]
    assert "poll:" not in str(message)


def test_without_a_liff_app_the_card_is_the_postback_card_as_before() -> None:
    message = build_poll_message(paged_poll())
    body = message["contents"]["body"]["contents"]
    assert [b["action"]["type"] for b in body[2:]] == ["postback", "postback"]
    assert body[2]["action"]["displayText"] == "Kyoto に投票"
    assert message == build_poll_message(paged_poll(), liff_id=None)


def test_a_poll_without_a_link_id_keeps_its_postback_card_even_with_a_liff_app() -> None:
    message = build_poll_message(paged_poll(link_id=""), liff_id="1234567890-AbCdEfGh")
    body = message["contents"]["body"]["contents"]
    assert [b["action"]["type"] for b in body[2:]] == ["postback", "postback"]


def test_the_alt_text_is_the_same_with_or_without_the_page() -> None:
    assert (
        build_poll_message(paged_poll(), liff_id="1234567890-AbCdEfGh")["altText"]
        == build_poll_message(paged_poll())["altText"]
    )
