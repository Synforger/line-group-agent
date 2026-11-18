import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.webhook.webhook_app import create_app
from tests.fakes import FakeLine
from tests.webhook.test_signature import SECRET, sign

pytestmark = pytest.mark.anyio
ALLOWED = "Callowed"
OTHER = "Cother"
PRIVATE_TEXT = "our secret plan for the trip"


class ScriptedAnswerer:
    def __init__(self, reply: str | None = "Sure.") -> None:
        self.reply = reply
        self.calls: list[tuple[str, GroupMessage]] = []

    async def answer(self, group_id: str, mention: GroupMessage) -> str | None:
        self.calls.append((group_id, mention))
        return self.reply


def text_event(
    group_id: str = ALLOWED,
    text: str = PRIVATE_TEXT,
    *,
    message_id: str = "m1",
    mentions_bot: bool = False,
) -> dict[str, Any]:
    message: dict[str, Any] = {"type": "text", "id": message_id, "text": text}
    if mentions_bot:
        message["mention"] = {
            "mentionees": [{"index": 0, "length": 4, "type": "user", "isSelf": True}]
        }
    return {
        "type": "message",
        "replyToken": "reply-token-1",
        "timestamp": 1_763_434_800_000,
        "source": {"type": "group", "groupId": group_id, "userId": "U1"},
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

    async def broken(group_id: str, mention: GroupMessage) -> str | None:
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
        async def answer(self, group_id: str, mention: GroupMessage) -> str | None:
            await release.wait()
            return "late"

    dispatcher = EventDispatcher(frozenset({ALLOWED}), line, GroupLog(tmp_path), BlockedAnswerer())
    body = json.dumps({"events": [text_event(mentions_bot=True)]}).encode()
    with TestClient(create_app(SECRET, 1024 * 1024, dispatcher)) as client:
        response = client.post(
            "/line/webhook", content=body, headers={"x-line-signature": sign(body)}
        )
        assert response.status_code == 200
        assert line.replies == []
