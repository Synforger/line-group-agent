"""A press on a poll card's button is counted as a vote; a poll that allows several picks
answers with one line through the reply token."""

from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.events.postback_handler import PostbackHandler
from line_group_agent.line_api.line_client import LineApiError, ReplyResult
from line_group_agent.polls.poll_book import PollBook
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import ALLOWED, OTHER, ScriptedAnswerer
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio


def postback_event(
    data: str = "poll:p1:1", group_id: str = ALLOWED, user_id: str | None = "U1"
) -> dict[str, Any]:
    source: dict[str, Any] = {"type": "group", "groupId": group_id}
    if user_id is not None:
        source["userId"] = user_id
    return {
        "type": "postback",
        "replyToken": "reply-token-1",
        "webhookEventId": "E1",
        "source": source,
        "postback": {"data": data},
    }


def setup(tmp_path: Path) -> tuple[EventDispatcher, FakeLine, GroupLog, PollBook]:
    line = FakeLine(names={"U1": "Aki"})
    group_log = GroupLog(tmp_path)
    book = PollBook(tmp_path, lambda: datetime(2026, 11, 18, 12, 0).astimezone())
    book.create(ALLOWED, "Where?", ["Kyoto", "Osaka"])
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        group_log,
        ScriptedAnswerer(),
        postbacks=PostbackHandler(book),
    )
    return dispatcher, line, group_log, book


async def test_a_press_in_a_one_pick_poll_is_counted_with_the_members_name_and_nothing_is_sent(
    tmp_path: Path,
) -> None:
    dispatcher, line, group_log, book = setup(tmp_path)
    await dispatcher.handle(postback_event())
    poll = book.get(ALLOWED, "p1")
    assert poll is not None
    assert [(v.user_id, v.name) for v in poll.options[1].voters] == [("U1", "Aki")]
    assert line.calls == []
    assert group_log.list_recent(ALLOWED, 10) == []


async def test_a_press_in_a_group_that_is_not_allowed_is_dropped(tmp_path: Path) -> None:
    dispatcher, _, _, book = setup(tmp_path)
    await dispatcher.handle(postback_event(group_id=OTHER))
    poll = book.get(ALLOWED, "p1")
    assert poll is not None and not any(o.voters for o in poll.options)


async def test_a_press_without_a_user_id_looks_up_no_name_and_counts_nothing(
    tmp_path: Path,
) -> None:
    dispatcher, line, _, book = setup(tmp_path)
    await dispatcher.handle(postback_event(user_id=None))
    poll = book.get(ALLOWED, "p1")
    assert poll is not None and not any(o.voters for o in poll.options)
    assert line.name_lookups == 0


async def test_without_a_handler_a_postback_is_ignored(tmp_path: Path) -> None:
    line = FakeLine()
    dispatcher = EventDispatcher(frozenset({ALLOWED}), line, GroupLog(tmp_path), ScriptedAnswerer())
    await dispatcher.handle(postback_event())
    assert line.calls == []


def setup_multiple(
    tmp_path: Path, line: FakeLine | None = None
) -> tuple[EventDispatcher, FakeLine]:
    line = line or FakeLine(names={"U1": "Aki"})
    book = PollBook(tmp_path, lambda: datetime(2026, 11, 18, 12, 0).astimezone())
    book.create(ALLOWED, "Which days?", ["Sat", "Sun"], multiple=True)
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        GroupLog(tmp_path),
        ScriptedAnswerer(),
        postbacks=PostbackHandler(book),
    )
    return dispatcher, line


async def test_a_press_in_a_poll_with_several_picks_is_answered_through_the_reply_token(
    tmp_path: Path,
) -> None:
    dispatcher, line = setup_multiple(tmp_path)
    await dispatcher.handle(postback_event("poll:p1:1"))
    [call] = line.calls
    assert (call.kind, call.target, call.text) == ("reply", "reply-token-1", "Aki: Sun")
    assert call.cards == [] and call.extras == [] and call.quote_token is None


async def test_the_answer_is_not_recorded_in_the_group_log(tmp_path: Path) -> None:
    dispatcher, _ = setup_multiple(tmp_path)
    await dispatcher.handle(postback_event("poll:p1:0"))
    assert dispatcher.group_log.list_recent(ALLOWED, 10) == []


async def test_a_refused_reply_token_is_not_pushed_instead(tmp_path: Path) -> None:
    dispatcher, line = setup_multiple(
        tmp_path, FakeLine(names={"U1": "Aki"}, reply_results=[ReplyResult.TOKEN_REFUSED])
    )
    await dispatcher.handle(postback_event("poll:p1:0"))
    assert [call.kind for call in line.calls] == ["reply"]


async def test_a_press_without_a_reply_token_is_counted_and_not_answered(tmp_path: Path) -> None:
    dispatcher, line = setup_multiple(tmp_path)
    event = postback_event("poll:p1:0")
    del event["replyToken"]
    await dispatcher.handle(event)
    assert line.calls == []


class FailingReplyLine(FakeLine):
    async def reply(self, *args: Any, **kwargs: Any) -> ReplyResult:
        await super().reply(*args, **kwargs)
        raise LineApiError("reply", 500)


async def test_a_failed_answer_to_a_press_does_not_lose_the_vote_or_push(tmp_path: Path) -> None:
    dispatcher, line = setup_multiple(tmp_path, FailingReplyLine(names={"U1": "Aki"}))
    await dispatcher.handle(postback_event("poll:p1:0"))
    assert [call.kind for call in line.calls] == ["reply"]
    poll = dispatcher.postbacks.polls.get(ALLOWED, "p1")  # type: ignore[union-attr]
    assert poll is not None and len(poll.options[0].voters) == 1
