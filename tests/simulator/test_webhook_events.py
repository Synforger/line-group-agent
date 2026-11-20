import json

from line_group_agent.events.event_fields import (
    is_self_mentioned,
    is_text_message,
    message_kind_of,
    postback_of,
    quote_token_of,
)
from line_group_agent.media.location_record import shared_location_line
from line_group_agent.simulator.webhook_events import (
    BotMention,
    EventIds,
    image_event,
    location_event,
    postback_event,
    sign_body,
    sticker_event,
    text_event,
    webhook_body,
)
from line_group_agent.stickers.sticker_record import received_sticker_line
from line_group_agent.webhook.signature import is_valid_signature

IDS = EventIds("reply-token", "EVENT1", "1001", "quote-token", 1_700_000_000_000)


def test_a_text_event_is_what_the_bot_reads_as_a_text_message_in_a_group() -> None:
    event = text_event("Cg", "Ua", "hello", IDS)
    assert is_text_message(event)
    assert event["source"] == {"type": "group", "groupId": "Cg", "userId": "Ua"}
    assert event["replyToken"] == "reply-token" and quote_token_of(event) == "quote-token"
    assert not is_self_mentioned(event)


def test_a_mention_puts_the_handle_first_and_marks_the_bot() -> None:
    event = text_event("Cg", "Ua", "hello", IDS, BotMention("Ubot", "Sora"))
    assert event["message"]["text"] == "@Sora hello"
    assert is_self_mentioned(event)
    [mentionee] = event["message"]["mention"]["mentionees"]
    assert (mentionee["index"], mentionee["length"]) == (0, len("@Sora"))


def test_a_sticker_event_is_read_by_the_bot_as_a_sticker_with_its_keywords() -> None:
    event = sticker_event(
        "Cg", "Ua", IDS, package_id="446", sticker_id="1988", keywords=["smile", "hello"]
    )
    assert message_kind_of(event) == "sticker" and not is_text_message(event)
    assert received_sticker_line(event["message"]) == "(スタンプ: smile、hello)"
    assert quote_token_of(event) == "quote-token"


def test_an_image_a_pin_and_a_postback_are_read_by_the_bot() -> None:
    assert message_kind_of(image_event("Cg", "Ua", IDS)) == "image"
    pin = location_event(
        "Cg", "Ua", IDS, title="Cafe", address="Kyoto", latitude=35.0, longitude=135.5
    )
    assert shared_location_line(pin["message"]) == "[位置] Cafe Kyoto (35.0, 135.5)"
    assert postback_of(postback_event("Cg", "Ub", "poll:p1:0", IDS)) == ("poll:p1:0", "Ub")


def test_the_signature_is_the_one_the_bot_accepts() -> None:
    body = webhook_body([text_event("Cg", "Ua", "こんにちは", IDS)], "Ubot")
    assert json.loads(body)["destination"] == "Ubot"
    signature = sign_body(body, "channel-secret")
    assert is_valid_signature(body, signature, "channel-secret")
    assert not is_valid_signature(body + b" ", signature, "channel-secret")
    assert not is_valid_signature(body, signature, "other-secret")
