"""Extra messages and quick replies in an answer reach LINE, and what LINE took is recorded."""

from pathlib import Path

import pytest

from line_group_agent.agent.answerer import Answer, SlowNotice
from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.line_api.line_client import ReplyResult
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem
from line_group_agent.records.group_log import GroupLog, GroupMessage
from tests.events.test_event_dispatcher import ALLOWED, text_event
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
PLACE = OutgoingExtra({"type": "location"}, "[位置] Gion Inn Kyoto (35.0, 135.0)")
POLL = OutgoingExtra({"type": "flex"}, "[投票] p1 Where? 1. Kyoto / 2. Osaka")
QUICK = [QuickReplyItem("Kyoto", "Sora、Kyoto")]


class ExtrasAnswerer:
    def __init__(self, answer: Answer) -> None:
        self.answer_to_give = answer

    async def answer(
        self, group_id: str, mention: GroupMessage, *, on_slow: SlowNotice | None = None
    ) -> Answer:
        return self.answer_to_give


def setup(
    tmp_path: Path, answer: Answer, **line_options: object
) -> tuple[EventDispatcher, FakeLine, GroupLog]:
    line = FakeLine(names={"U1": "Aki"}, **line_options)  # type: ignore[arg-type]
    group_log = GroupLog(tmp_path)
    dispatcher = EventDispatcher(frozenset({ALLOWED}), line, group_log, ExtrasAnswerer(answer))
    return dispatcher, line, group_log


async def test_the_extras_and_quick_replies_are_sent_with_the_reply(tmp_path: Path) -> None:
    answer = Answer("Here.", extras=[POLL, PLACE], quick_replies=QUICK)
    dispatcher, line, _ = setup(tmp_path, answer)
    await dispatcher.handle(text_event(mentions_bot=True))
    [call] = line.calls
    assert call.kind == "reply" and call.extras == [POLL, PLACE] and call.quick_replies == QUICK


async def test_the_record_of_the_reply_names_each_extra_after_the_text(tmp_path: Path) -> None:
    answer = Answer("Here.", extras=[POLL, PLACE])
    dispatcher, _, group_log = setup(tmp_path, answer)
    await dispatcher.handle(text_event(mentions_bot=True))
    reply = group_log.list_recent(ALLOWED, 10)[-1]
    assert reply.from_bot
    assert reply.text == f"Here.\n{POLL.record_line}\n{PLACE.record_line}"


async def test_an_extra_alone_is_sent_and_recorded(tmp_path: Path) -> None:
    dispatcher, line, group_log = setup(tmp_path, Answer(None, extras=[POLL]))
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.calls[0].text is None and line.calls[0].extras == [POLL]
    assert group_log.list_recent(ALLOWED, 10)[-1].text == POLL.record_line


async def test_extras_that_LINE_refuses_are_not_recorded(tmp_path: Path) -> None:
    refused = [ReplyResult.MESSAGE_REFUSED, ReplyResult.MESSAGE_REFUSED]
    dispatcher, _, group_log = setup(
        tmp_path, Answer("Here.", extras=[POLL]), reply_results=refused
    )
    await dispatcher.handle(text_event(mentions_bot=True))
    assert group_log.list_recent(ALLOWED, 10)[-1].text == "Here."
