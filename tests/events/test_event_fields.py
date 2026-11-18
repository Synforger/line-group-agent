from datetime import datetime

from line_group_agent.events.event_fields import (
    group_id_of,
    is_self_mentioned,
    is_text_message,
    local_time_of,
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
