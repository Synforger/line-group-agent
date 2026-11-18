"""A member who joins an allowed group is welcomed with a fixed text, when one is set."""

from pathlib import Path
from typing import Any

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher, NoticeTexts
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import ALLOWED, OTHER, ScriptedAnswerer
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio


def member_joined_event(group_id: str = ALLOWED) -> dict[str, Any]:
    return {
        "type": "memberJoined",
        "replyToken": "welcome-token",
        "timestamp": 1_763_434_800_000,
        "source": {"type": "group", "groupId": group_id},
        "joined": {"members": [{"type": "user", "userId": "U9"}]},
    }


def setup(tmp_path: Path, texts: NoticeTexts) -> tuple[EventDispatcher, FakeLine, GroupLog]:
    line = FakeLine()
    group_log = GroupLog(tmp_path)
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}), line, group_log, ScriptedAnswerer(), texts=texts
    )
    return dispatcher, line, group_log


async def test_a_new_member_is_welcomed_through_the_reply_token_and_it_is_recorded(
    tmp_path: Path,
) -> None:
    dispatcher, line, group_log = setup(tmp_path, NoticeTexts(welcome="Welcome! Ask me anything."))
    await dispatcher.handle(member_joined_event())
    assert line.replies == [("welcome-token", "Welcome! Ask me anything.")]
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.from_bot and recorded.text == "Welcome! Ask me anything."


async def test_without_a_welcome_text_nothing_is_sent(tmp_path: Path) -> None:
    dispatcher, line, group_log = setup(tmp_path, NoticeTexts(intro="Hello."))
    await dispatcher.handle(member_joined_event())
    assert line.calls == [] and group_log.list_recent(ALLOWED, 10) == []


async def test_the_welcome_and_the_introduction_are_separate_texts(tmp_path: Path) -> None:
    dispatcher, line, _ = setup(tmp_path, NoticeTexts(intro="Hello.", welcome="Welcome!"))
    join = {"type": "join", "replyToken": "t", "source": {"type": "group", "groupId": ALLOWED}}
    await dispatcher.handle(join)
    await dispatcher.handle(member_joined_event())
    assert [text for _, text in line.replies] == ["Hello.", "Welcome!"]


async def test_a_member_joining_a_group_that_is_not_allowed_gets_nothing(tmp_path: Path) -> None:
    dispatcher, line, _ = setup(tmp_path, NoticeTexts(welcome="Welcome!"))
    await dispatcher.handle(member_joined_event(OTHER))
    assert line.calls == []
