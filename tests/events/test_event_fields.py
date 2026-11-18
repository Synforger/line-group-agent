from datetime import datetime

from line_group_agent.events.event_fields import (
    age_seconds_of,
    group_id_of,
    is_called_by_name,
    is_redelivery,
    is_self_mentioned,
    is_text_message,
    local_time_of,
    quote_token_of,
    unsent_message_id_of,
)


def text_event(**message: object) -> dict:
    return {
        "type": "message",
        "source": {"type": "group", "groupId": "Cg", "userId": "U1"},
        "message": {"type": "text", "id": "1", "text": "hi", **message},
    }


def test_group_id_comes_from_a_group_source() -> None:
    assert group_id_of(text_event()) == "Cg"
    assert group_id_of({"source": {"type": "user", "userId": "U1"}}) is None
    assert group_id_of({"source": {"type": "room", "roomId": "R1"}}) is None
    assert group_id_of({}) is None


def test_only_text_messages_are_text() -> None:
    assert is_text_message(text_event())
    assert not is_text_message({**text_event(), "message": {"type": "image", "id": "1"}})
    assert not is_text_message({"type": "join", "source": {"type": "group", "groupId": "Cg"}})


def test_a_mention_marked_is_self_mentions_the_bot() -> None:
    mention = {"mentionees": [{"index": 0, "length": 4, "type": "user", "isSelf": True}]}
    assert is_self_mentioned(text_event(mention=mention))


def test_a_mention_of_someone_else_does_not() -> None:
    mention = {"mentionees": [{"type": "user", "userId": "U2", "isSelf": False}]}
    assert not is_self_mentioned(text_event(mention=mention))


def test_mention_all_does_not() -> None:
    assert not is_self_mentioned(text_event(mention={"mentionees": [{"type": "all"}]}))


def test_the_bots_name_in_text_alone_does_not() -> None:
    assert not is_self_mentioned(text_event(text="@bot what about Kyoto?"))


def test_is_self_must_be_true_not_truthy() -> None:
    mention = {"mentionees": [{"type": "user", "isSelf": "true"}]}
    assert not is_self_mentioned(text_event(mention=mention))


def test_the_time_is_local_iso_from_the_millisecond_timestamp() -> None:
    stamp = local_time_of({"timestamp": 1_763_434_800_000})
    assert datetime.fromisoformat(stamp).timestamp() == 1_763_434_800
    assert datetime.fromisoformat(stamp).utcoffset() is not None


def test_redelivery_comes_from_the_delivery_context() -> None:
    assert is_redelivery({"deliveryContext": {"isRedelivery": True}})
    assert not is_redelivery({"deliveryContext": {"isRedelivery": False}})
    assert not is_redelivery({})


def test_age_is_counted_from_the_millisecond_timestamp() -> None:
    now = datetime.fromtimestamp(1_000).astimezone()
    assert age_seconds_of({"timestamp": 400_000}, now) == 600
    assert age_seconds_of({}, now) is None


def test_the_quote_token_is_read_from_a_text_message() -> None:
    event = {"message": {"type": "text", "quoteToken": "q1"}}
    assert quote_token_of(event) == "q1"
    assert quote_token_of({"message": {"type": "text"}}) is None
    assert quote_token_of({"message": {"quoteToken": ""}}) is None
    assert quote_token_of({}) is None


def test_an_unsend_event_gives_the_id_of_the_message_taken_back() -> None:
    event = {"type": "unsend", "unsend": {"messageId": "m7"}}
    assert unsent_message_id_of(event) == "m7"
    assert unsent_message_id_of({"type": "message", "unsend": {"messageId": "m7"}}) is None
    assert unsent_message_id_of({"type": "unsend", "unsend": {}}) is None
    assert unsent_message_id_of({"type": "unsend"}) is None


NAMES = ("ソラ", "そら", "sora")


def said(text: str) -> dict:
    return {"type": "message", "message": {"type": "text", "id": "1", "text": text}}


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "text",
    [
        "ソラ、明日の天気は?",
        "そら 店探して",
        "SORA what's good here",
        "明日どこ行く?ソラ",
        "sora!",
        "  ソラ  ",
    ],
)
def test_a_name_at_the_start_or_end_calls_the_bot(text: str) -> None:
    assert is_called_by_name(said(text), NAMES)


@pytest.mark.parametrize(
    "text",
    [
        "昨日ソラに聞いたら便利だった",
        "ソラって便利だね",
        "Soraya Live",
        "malsora の薬",
        "普通",
        "",
    ],
)
def test_a_name_in_the_middle_or_inside_a_word_does_not(text: str) -> None:
    assert not is_called_by_name(said(text), NAMES)


def test_no_names_means_no_call() -> None:
    assert not is_called_by_name(said("ソラ、ねえ"), ())
