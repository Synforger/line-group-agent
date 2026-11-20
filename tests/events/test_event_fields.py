from datetime import datetime

from line_group_agent.events.event_fields import (
    age_seconds_of,
    group_id_of,
    is_called_by_name,
    is_external_image,
    is_name_in_text,
    is_redelivery,
    is_self_mentioned,
    is_text_message,
    local_time_of,
    message_kind_of,
    postback_of,
    quote_token_of,
    strip_call_name,
    unsent_message_id_of,
    webhook_event_id_of,
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


@pytest.mark.parametrize(
    "text",
    [
        "あ、やっぱ嵐山がよかった。ソラ、さっきの変更戻せる?",
        "そっか!  ソラ 店探して",
        "えー\nsora、おすすめは?",
        "どうする?\u3000ソラ、決めて",
    ],
)
def test_a_name_at_the_start_of_a_later_sentence_calls_the_bot(text: str) -> None:
    assert is_called_by_name(said(text), NAMES)


@pytest.mark.parametrize(
    "text",
    [
        "あ、やっぱ嵐山がよかった。昨日ソラに聞いた",
        "やった!ソラって便利だね",
        "えー\nSoraya Live",
    ],
)
def test_a_name_inside_a_later_sentence_or_glued_to_the_text_does_not(text: str) -> None:
    assert not is_called_by_name(said(text), NAMES)


def test_no_names_means_no_call() -> None:
    assert not is_called_by_name(said("ソラ、ねえ"), ())


def test_a_postback_gives_its_data_and_who_pressed() -> None:
    event = {
        "type": "postback",
        "source": {"type": "group", "groupId": "Cg", "userId": "U1"},
        "postback": {"data": "poll:p1:0"},
    }
    assert postback_of(event) == ("poll:p1:0", "U1")
    without_user = {**event, "source": {"type": "group", "groupId": "Cg"}}
    assert postback_of(without_user) == ("poll:p1:0", None)


def test_an_event_that_is_not_a_postback_with_data_gives_none() -> None:
    assert postback_of(text_event()) is None
    assert postback_of({"type": "postback", "postback": {}}) is None
    assert postback_of({"type": "postback", "postback": {"data": ""}}) is None


def test_the_webhook_event_id_is_read_when_there_is_one() -> None:
    assert webhook_event_id_of({"webhookEventId": "01H"}) == "01H"
    assert webhook_event_id_of({"webhookEventId": ""}) is None
    assert webhook_event_id_of({}) is None


def test_a_call_name_at_either_end_is_removed_with_the_punctuation_next_to_it() -> None:
    assert strip_call_name("Sora, itinerary", ("Sora",)) == "itinerary"
    assert strip_call_name("itinerary、 SORA!", ("sora",)) == "itinerary"
    assert strip_call_name("itinerary", ("Sora",)) == "itinerary"
    assert strip_call_name("itinerary", ()) == "itinerary"


def test_text_and_image_messages_are_the_kinds_the_agent_records() -> None:
    assert message_kind_of(text_event()) == "text"
    image = {**text_event(), "message": {"type": "image", "id": "1"}}
    assert message_kind_of(image) == "image"


def test_a_location_message_is_a_kind_too() -> None:
    location = {**text_event(), "message": {"type": "location", "id": "1"}}
    assert message_kind_of(location) == "location"


def test_a_sticker_message_is_a_kind_too() -> None:
    sticker = {**text_event(), "message": {"type": "sticker", "id": "1"}}
    assert message_kind_of(sticker) == "sticker"


def test_other_messages_and_events_have_no_kind() -> None:
    assert message_kind_of({**text_event(), "message": {"type": "video", "id": "1"}}) is None
    assert message_kind_of({"type": "join"}) is None
    assert message_kind_of({"type": "postback", "message": {"type": "image"}}) is None


def test_an_image_at_an_outside_address_is_external() -> None:
    line = {"message": {"type": "image", "contentProvider": {"type": "line"}}}
    outside = {"message": {"type": "image", "contentProvider": {"type": "external"}}}
    assert not is_external_image(line) and is_external_image(outside)
    assert not is_external_image({"message": {"type": "image"}})


@pytest.mark.parametrize(
    "text",
    [
        "昨日ソラに聞いたら便利だった",
        "ソラって便利だね",
        "ソラ、明日どこ行く?",
        "明日どこ行く?ソラ",
        "this is sora talking",
        "Ask SORA, then decide",
        "soraya and sora",
    ],
)
def test_a_name_anywhere_in_the_text_is_found(text: str) -> None:
    assert is_name_in_text(said(text), NAMES)


@pytest.mark.parametrize(
    "text",
    [
        "Soraya Live",
        "malsora の薬",
        "mysorax",
        "sora2",
        "普通の話",
        "",
    ],
)
def test_a_latin_name_inside_a_longer_word_is_not_found(text: str) -> None:
    assert not is_name_in_text(said(text), NAMES)


def test_no_names_or_no_text_finds_nothing() -> None:
    assert not is_name_in_text(said("ソラ"), ())
    assert not is_name_in_text({"type": "message", "message": {"type": "image"}}, NAMES)


@pytest.mark.parametrize(
    "text", ["ソラ候補出して", "そら投票作って", "ソラliff使って", "Sora、ねえ", "SORA what's good"]
)
def test_with_start_runs_on_a_name_glued_to_the_text_at_the_start_calls(text: str) -> None:
    assert is_called_by_name(said(text), NAMES, start_runs_on=True)


@pytest.mark.parametrize("text", ["Soraya Live", "昨日ソラに聞いた"])
def test_with_start_runs_on_a_latin_word_or_a_name_in_the_middle_still_does_not(
    text: str,
) -> None:
    assert not is_called_by_name(said(text), NAMES, start_runs_on=True)


def test_with_start_runs_on_a_glued_name_at_the_start_of_a_later_sentence_calls() -> None:
    text = "あ、やっぱ嵐山がよかった。ソラ候補出して"
    assert is_called_by_name(said(text), NAMES, start_runs_on=True)
    assert not is_called_by_name(said(text), NAMES)


def test_without_start_runs_on_a_glued_name_at_the_start_does_not_call() -> None:
    assert not is_called_by_name(said("ソラ候補出して"), NAMES)
