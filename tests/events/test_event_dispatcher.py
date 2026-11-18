import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from line_group_agent.agent.answerer import Answer, SlowNotice
from line_group_agent.cards.card import Card
from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.line_api.line_client import ReplyResult
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.webhook.webhook_app import create_app
from tests.fakes import FakeLine
from tests.webhook.test_signature import SECRET, sign

pytestmark = pytest.mark.anyio
ALLOWED = "Callowed"
OTHER = "Cother"
PRIVATE_TEXT = "our secret plan for the trip"


class ScriptedAnswerer:
    def __init__(self, reply: str | None = "Sure.", cards: list[Card] | None = None) -> None:
        self.reply = reply
        self.cards = cards or []
        self.calls: list[tuple[str, GroupMessage]] = []

    async def answer(
        self, group_id: str, mention: GroupMessage, *, on_slow: SlowNotice | None = None
    ) -> Answer:
        self.calls.append((group_id, mention))
        return Answer(self.reply, self.cards, record=self.record)

    record = True


def text_event(
    group_id: str = ALLOWED,
    text: str = PRIVATE_TEXT,
    *,
    message_id: str = "m1",
    mentions_bot: bool = False,
    user_id: str = "U1",
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "type": "text",
        "id": message_id,
        "text": text,
        "quoteToken": f"quote-{message_id}",
    }
    if mentions_bot:
        message["mention"] = {
            "mentionees": [{"index": 0, "length": 4, "type": "user", "isSelf": True}]
        }
    return {
        "type": "message",
        "replyToken": "reply-token-1",
        "timestamp": 1_763_434_800_000,
        "source": {"type": "group", "groupId": group_id, "userId": user_id},
        "message": message,
    }


def setup(
    tmp_path: Path, **line_options: Any
) -> tuple[EventDispatcher, FakeLine, GroupLog, ScriptedAnswerer]:
    line = FakeLine(names={"U1": "Aki"}, **line_options)
    group_log = GroupLog(tmp_path)
    answerer = ScriptedAnswerer()
    dispatcher = EventDispatcher(frozenset({ALLOWED}), line, group_log, answerer)
    return dispatcher, line, group_log, answerer


async def test_a_text_message_of_an_allowed_group_is_recorded(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    await dispatcher.handle(text_event())
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.text == PRIVATE_TEXT
    assert recorded.user_id == "U1" and recorded.display_name == "Aki"
    assert recorded.message_id == "m1"
    assert answerer.calls == []
    assert line.replies == [] and line.pushes == []


async def test_member_names_are_looked_up_once(tmp_path: Path) -> None:
    dispatcher, line, *_ = setup(tmp_path)
    await dispatcher.handle(text_event(message_id="1"))
    await dispatcher.handle(text_event(message_id="2"))
    assert line.name_lookups == 1


async def test_a_mention_of_the_bot_is_answered_by_reply(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    await dispatcher.handle(text_event(mentions_bot=True))
    assert answerer.calls[0][0] == ALLOWED
    assert line.replies == [("reply-token-1", "Sure.")]
    assert line.pushes == []


async def test_the_sent_reply_is_recorded_as_the_bots_own_message(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    await dispatcher.handle(text_event(mentions_bot=True))
    mention, reply = group_log.list_recent(ALLOWED, 10)
    assert not mention.from_bot
    assert reply.from_bot and reply.text == "Sure."
    assert reply.message_id.startswith("bot-")


async def test_a_pushed_reply_is_recorded_too(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path, reply_accepts=False)
    await dispatcher.handle(text_event(mentions_bot=True))
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False, True]


async def test_nothing_is_recorded_for_the_bot_when_nothing_is_sent(tmp_path: Path) -> None:
    dispatcher, _, group_log, answerer = setup(tmp_path)
    answerer.reply = None
    await dispatcher.handle(text_event(mentions_bot=True))
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False]


async def test_the_bots_name_without_a_mention_is_not_answered(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    await dispatcher.handle(text_event(text="@bot are you there?"))
    assert answerer.calls == []


async def test_nothing_is_sent_when_the_answer_has_no_reply(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    answerer.reply = None
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.replies == [] and line.pushes == []


async def test_a_refused_reply_token_falls_back_to_one_push(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher, line, *_ = setup(tmp_path, reply_accepts=False)
    with caplog.at_level(logging.INFO):
        await dispatcher.handle(text_event(mentions_bot=True))
    assert line.pushes == [(ALLOWED, "Sure.")]
    assert len([r for r in caplog.records if "push" in r.getMessage()]) == 1


def redelivered(event: dict[str, Any], *, age_seconds: float) -> dict[str, Any]:
    now_ms = int(datetime.now().timestamp() * 1000)
    return {
        **event,
        "timestamp": now_ms - int(age_seconds * 1000),
        "deliveryContext": {"isRedelivery": True},
    }


async def test_a_message_that_arrives_again_is_recorded_and_answered_once(
    tmp_path: Path,
) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    event = text_event(mentions_bot=True)
    await dispatcher.handle(event)
    await dispatcher.handle(redelivered(event, age_seconds=5))
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False, True]
    assert len(answerer.calls) == 1
    assert len(line.replies) == 1 and line.pushes == []


async def test_a_redelivered_mention_inside_the_window_is_answered(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path, reply_accepts=False)
    await dispatcher.handle(redelivered(text_event(mentions_bot=True), age_seconds=60))
    assert len(answerer.calls) == 1
    assert line.pushes == [(ALLOWED, "Sure.")]


async def test_a_redelivered_mention_past_the_window_is_recorded_but_not_answered(
    tmp_path: Path,
) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    await dispatcher.handle(redelivered(text_event(mentions_bot=True), age_seconds=601))
    assert len(group_log.list_recent(ALLOWED, 10)) == 1
    assert answerer.calls == []
    assert line.replies == [] and line.pushes == []


async def test_an_old_mention_delivered_the_first_time_is_still_answered(
    tmp_path: Path,
) -> None:
    dispatcher, _, _, answerer = setup(tmp_path)
    await dispatcher.handle(text_event(mentions_bot=True))  # timestamp from 2025
    assert len(answerer.calls) == 1


async def test_events_of_other_groups_are_dropped_and_only_their_id_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    with caplog.at_level(logging.INFO):
        await dispatcher.handle(text_event(group_id=OTHER, mentions_bot=True))
        await dispatcher.handle(text_event(group_id=OTHER, message_id="m2"))
    assert answerer.calls == [] and line.replies == []
    assert not (tmp_path / "groups" / OTHER).exists()
    assert OTHER in caplog.text
    assert PRIVATE_TEXT not in caplog.text
    assert len(caplog.records) == 1


async def test_joining_an_unknown_group_logs_its_id(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher, *_ = setup(tmp_path)
    join = {"type": "join", "replyToken": "t", "source": {"type": "group", "groupId": OTHER}}
    with caplog.at_level(logging.INFO):
        await dispatcher.handle(join)
    assert f"group_id={OTHER}" in caplog.text


async def test_one_to_one_chats_are_dropped(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    event = text_event(mentions_bot=True)
    event["source"] = {"type": "user", "userId": "U1"}
    await dispatcher.handle(event)
    assert answerer.calls == [] and line.replies == []
    assert not (tmp_path / "groups").exists()


async def test_non_text_messages_are_not_recorded(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    event = text_event()
    event["message"] = {"type": "image", "id": "m9"}
    await dispatcher.handle(event)
    assert group_log.list_recent(ALLOWED, 10) == []


async def test_the_worker_handles_queued_events_and_survives_a_failure(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)

    async def broken(group_id: str, mention: GroupMessage, **_: Any) -> Answer:
        raise RuntimeError(PRIVATE_TEXT)

    answerer.answer = broken  # type: ignore[method-assign]
    dispatcher.start()
    try:
        dispatcher.add_events([text_event(mentions_bot=True), text_event(message_id="m2"), "x"])
        await asyncio.wait_for(dispatcher.wait_idle(), timeout=5)
    finally:
        await dispatcher.stop()
    assert len(group_log.list_recent(ALLOWED, 10)) == 2
    assert "RuntimeError" in caplog.text
    assert PRIVATE_TEXT not in caplog.text


def test_the_webhook_answers_200_before_the_answer_is_ready(tmp_path: Path) -> None:
    line = FakeLine()
    release = asyncio.Event()

    class BlockedAnswerer:
        async def answer(
            self, group_id: str, mention: GroupMessage, *, on_slow: SlowNotice | None = None
        ) -> Answer:
            await release.wait()
            return Answer("late")

    dispatcher = EventDispatcher(frozenset({ALLOWED}), line, GroupLog(tmp_path), BlockedAnswerer())
    body = json.dumps({"events": [text_event(mentions_bot=True)]}).encode()
    with TestClient(create_app(SECRET, 1024 * 1024, dispatcher)) as client:
        response = client.post(
            "/line/webhook", content=body, headers={"x-line-signature": sign(body)}
        )
        assert response.status_code == 200
        assert line.replies == []


CARDS = [
    Card("Gion Inn", "x", "https://example.com/1", price="¥2,980〜"),
    Card("River Hotel", "y", "https://example.com/2"),
]


async def test_sent_cards_are_added_to_the_bots_record_after_its_text(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    answerer.cards = CARDS
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.calls[0].cards == CARDS
    _, reply = group_log.list_recent(ALLOWED, 10)
    assert reply.from_bot
    assert reply.text == (
        "Sure.\n[カード] 1. Gion Inn (¥2,980〜) https://example.com/1 / 2. River Hotel https://example.com/2"
    )


async def test_cards_with_no_text_are_sent_and_recorded(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    answerer.reply, answerer.cards = None, CARDS
    await dispatcher.handle(text_event(mentions_bot=True))
    assert len(line.calls) == 1
    _, reply = group_log.list_recent(ALLOWED, 10)
    assert reply.text.startswith("[カード] 1. Gion Inn")


async def test_cards_that_had_to_be_dropped_are_not_recorded_as_sent(tmp_path: Path) -> None:
    dispatcher, _, group_log, answerer = setup(
        tmp_path, reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.MESSAGE_REFUSED]
    )
    answerer.cards = CARDS
    await dispatcher.handle(text_event(mentions_bot=True))
    _, reply = group_log.list_recent(ALLOWED, 10)
    assert reply.text == "Sure."


async def test_nothing_is_recorded_when_a_cards_only_answer_cannot_be_sent(
    tmp_path: Path,
) -> None:
    dispatcher, _, group_log, answerer = setup(
        tmp_path, reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.MESSAGE_REFUSED]
    )
    answerer.reply, answerer.cards = None, CARDS
    await dispatcher.handle(text_event(mentions_bot=True))
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False]


OPERATOR = "Uoperator"


def guarded(tmp_path: Path, present: bool | None) -> tuple[EventDispatcher, FakeLine]:
    line = FakeLine(members={OPERATOR: present})
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        GroupLog(tmp_path),
        ScriptedAnswerer(),
        required_member_user_id=OPERATOR,
    )
    return dispatcher, line


def join_event(group_id: str = OTHER) -> dict[str, Any]:
    return {"type": "join", "replyToken": "t", "source": {"type": "group", "groupId": group_id}}


async def test_a_group_without_the_required_member_is_left_at_once(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher, line = guarded(tmp_path, present=False)
    with caplog.at_level(logging.INFO):
        await dispatcher.handle(join_event())
    assert line.left_groups == [OTHER]
    assert "left a group" in caplog.text and f"group_id={OTHER}" in caplog.text
    assert line.calls == []


async def test_a_group_whose_membership_is_unknown_is_left_too(tmp_path: Path) -> None:
    dispatcher, line = guarded(tmp_path, present=None)
    await dispatcher.handle(join_event())
    assert line.left_groups == [OTHER]


async def test_a_group_with_the_required_member_is_kept_and_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dispatcher, line = guarded(tmp_path, present=True)
    with caplog.at_level(logging.INFO):
        await dispatcher.handle(join_event())
    assert line.left_groups == []
    assert f"joined a group that is not allowed: group_id={OTHER}" in caplog.text


async def test_a_message_from_an_unknown_group_also_triggers_the_check_once(
    tmp_path: Path,
) -> None:
    dispatcher, line = guarded(tmp_path, present=False)
    await dispatcher.handle(text_event(group_id=OTHER, mentions_bot=True))
    await dispatcher.handle(text_event(group_id=OTHER, message_id="m2"))
    assert line.left_groups == [OTHER]
    assert line.calls == []


async def test_allowed_groups_are_never_checked_or_left(tmp_path: Path) -> None:
    dispatcher, line = guarded(tmp_path, present=False)
    await dispatcher.handle(join_event(ALLOWED))
    await dispatcher.handle(text_event())
    assert line.left_groups == []


async def test_without_a_required_member_unknown_groups_are_kept(tmp_path: Path) -> None:
    dispatcher, line, *_ = setup(tmp_path)
    await dispatcher.handle(join_event())
    assert line.left_groups == []


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def auto_allowing(
    tmp_path: Path, present: bool | None
) -> tuple[EventDispatcher, FakeLine, GroupLog, ScriptedAnswerer, Clock]:
    line = FakeLine(members={OPERATOR: present})
    group_log = GroupLog(tmp_path)
    answerer = ScriptedAnswerer()
    clock = Clock()
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        group_log,
        answerer,
        required_member_user_id=OPERATOR,
        allow_groups_with_required_member=True,
        clock=clock,
    )
    return dispatcher, line, group_log, answerer, clock


async def test_a_group_the_member_is_in_is_recorded_and_answered(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer, _ = auto_allowing(tmp_path, present=True)
    await dispatcher.handle(join_event())
    await dispatcher.handle(text_event(group_id=OTHER, mentions_bot=True))
    assert line.left_groups == []
    assert len(answerer.calls) == 1
    assert [m.from_bot for m in group_log.list_recent(OTHER, 10)] == [False, True]


async def test_a_group_the_member_is_not_in_is_left_in_auto_mode(tmp_path: Path) -> None:
    dispatcher, line, _, answerer, _ = auto_allowing(tmp_path, present=False)
    await dispatcher.handle(join_event())
    await dispatcher.handle(text_event(group_id=OTHER, mentions_bot=True))
    assert line.left_groups == [OTHER]
    assert answerer.calls == []


async def test_membership_is_asked_again_after_an_hour_and_the_bot_leaves(
    tmp_path: Path,
) -> None:
    dispatcher, line, _, answerer, clock = auto_allowing(tmp_path, present=True)
    await dispatcher.handle(text_event(group_id=OTHER, message_id="1"))
    line.members[OPERATOR] = False
    clock.now = 3599
    await dispatcher.handle(text_event(group_id=OTHER, message_id="2"))
    assert line.left_groups == []
    clock.now = 3601
    await dispatcher.handle(text_event(group_id=OTHER, message_id="3", mentions_bot=True))
    assert line.left_groups == [OTHER]
    assert answerer.calls == []


class RecordingObserver:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def note_message(self, group_id: str, message: GroupMessage) -> None:
        self.calls.append(("message", message.message_id))

    async def after_answer(self, group_id: str) -> None:
        self.calls.append(("answered", group_id))

    async def after_deletion(self, group_id: str) -> None:
        self.calls.append(("deleted", group_id))


def observed(tmp_path: Path, **line_options: Any) -> tuple[EventDispatcher, RecordingObserver]:
    observer = RecordingObserver()
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        FakeLine(names={"U1": "Aki"}, **line_options),
        GroupLog(tmp_path),
        ScriptedAnswerer(),
        observer=observer,
    )
    return dispatcher, observer


async def test_the_observer_hears_of_each_recorded_message_and_each_answer(tmp_path: Path) -> None:
    dispatcher, observer = observed(tmp_path)
    await dispatcher.handle(text_event(message_id="m1"))
    await dispatcher.handle(text_event(message_id="m2", mentions_bot=True))
    await dispatcher.handle(text_event(message_id="m2", mentions_bot=True))
    assert observer.calls == [("message", "m1"), ("message", "m2"), ("answered", ALLOWED)]


async def test_the_observer_hears_of_the_answer_even_when_sending_it_failed(
    tmp_path: Path,
) -> None:
    dispatcher, observer = observed(tmp_path, reply_accepts=False, push_statuses=[500])
    with pytest.raises(Exception, match="push"):
        await dispatcher.handle(text_event(mentions_bot=True))
    assert ("answered", ALLOWED) in observer.calls


async def test_a_group_that_is_not_allowed_is_not_reported_to_the_observer(
    tmp_path: Path,
) -> None:
    dispatcher, observer = observed(tmp_path)
    await dispatcher.handle(text_event(OTHER))
    assert observer.calls == []


async def test_a_notice_that_took_no_turn_is_sent_but_not_recorded(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path)
    answerer.record = False
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.replies == [("reply-token-1", "Sure.")]
    assert [m.from_bot for m in group_log.list_recent(ALLOWED, 10)] == [False]
