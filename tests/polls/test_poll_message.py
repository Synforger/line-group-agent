from line_group_agent.polls.poll import KIND_DATE, Poll, PollOption
from line_group_agent.polls.poll_message import (
    CHOICE_HINT,
    DATE_HINT,
    MULTIPLE_HINT,
    build_poll_message,
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
        {"type": "postback", "label": "Kyoto", "data": "poll:p3:0"},
        {"type": "postback", "label": "Osaka", "data": "poll:p3:1"},
    ]
    assert "displayText" not in body[2]["action"]


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
