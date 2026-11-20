from pathlib import Path
from typing import Any

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import ALLOWED, ScriptedAnswerer
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio


def sticker_event(**message: Any) -> dict[str, Any]:
    return {
        "type": "message",
        "replyToken": "reply-token-1",
        "timestamp": 1_763_434_800_000,
        "source": {"type": "group", "groupId": ALLOWED, "userId": "U1"},
        "message": {
            "type": "sticker",
            "id": "s1",
            "quoteToken": "q-s1",
            "packageId": "446",
            "stickerId": "1988",
            **message,
        },
    }


def setup(tmp_path: Path) -> tuple[EventDispatcher, FakeLine, GroupLog, ScriptedAnswerer]:
    line = FakeLine(names={"U1": "Aki"})
    group_log = GroupLog(tmp_path)
    answerer = ScriptedAnswerer()
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}), line, group_log, answerer, call_names=("Sora",)
    )
    return dispatcher, line, group_log, answerer


async def test_a_sticker_is_recorded_with_its_keywords(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    await dispatcher.handle(sticker_event(keywords=["thanks", "ありがとう"]))
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.text == "(スタンプ: thanks、ありがとう)"
    assert recorded.user_id == "U1" and recorded.display_name == "Aki"


async def test_a_sticker_without_keywords_is_recorded_as_a_sticker(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    await dispatcher.handle(sticker_event())
    assert [m.text for m in group_log.list_recent(ALLOWED, 10)] == ["(スタンプ)"]


async def test_a_sticker_alone_never_calls_the_bot(tmp_path: Path) -> None:
    dispatcher, line, _, answerer = setup(tmp_path)
    # Even a message sticker whose text holds the bot's name, and one that quotes the bot.
    await dispatcher.handle(sticker_event(text="Sora", keywords=["Sora"]))
    assert answerer.calls == []
    assert line.replies == [] and line.pushes == []


async def test_a_sticker_sent_again_is_recorded_once(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    await dispatcher.handle(sticker_event())
    await dispatcher.handle(sticker_event())
    assert len(group_log.list_recent(ALLOWED, 10)) == 1
