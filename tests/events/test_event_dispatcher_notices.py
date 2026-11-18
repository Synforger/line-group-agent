"""The dispatcher's fixed texts and limits around a mention: quote, error text, hourly
limit, the wait notice, the introduction and the alert for a failed send."""

from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.answerer import Answer, SlowNotice
from line_group_agent.alerts.alert_notifier import ALERT_TEXTS, AlertKind, AlertNotifier
from line_group_agent.events.event_dispatcher import EventDispatcher, NoticeTexts
from line_group_agent.events.mention_limiter import MentionLimiter
from line_group_agent.events.wait_notice import WaitNotice
from line_group_agent.line_api.line_client import ReplyResult
from line_group_agent.line_api.push_quota import PushQuota
from line_group_agent.records.group_log import GroupLog, GroupMessage
from tests.events.test_event_dispatcher import (
    ALLOWED,
    OTHER,
    ScriptedAnswerer,
    join_event,
    text_event,
)
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
OPERATOR = "Uoperator"
TEXTS = NoticeTexts(
    error="Sorry, something broke.", rate_limit="Too many asks.", intro="Hello, I am the helper."
)


class SlowAnswerer(ScriptedAnswerer):
    """An answerer that says it will take a while before it answers."""

    async def answer(
        self, group_id: str, mention: GroupMessage, *, on_slow: SlowNotice | None = None
    ) -> Answer:
        if on_slow is not None:
            await on_slow()
        return await super().answer(group_id, mention, on_slow=on_slow)


def build(
    tmp_path: Path,
    answerer: ScriptedAnswerer | None = None,
    *,
    line: FakeLine | None = None,
    **options: Any,
) -> tuple[EventDispatcher, FakeLine, GroupLog]:
    line = line or FakeLine(names={"U1": "Aki"})
    group_log = GroupLog(tmp_path)
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        group_log,
        answerer or ScriptedAnswerer(),
        texts=TEXTS,
        **options,
    )
    return dispatcher, line, group_log


async def test_the_reply_quotes_the_message_that_called_the_bot(tmp_path: Path) -> None:
    dispatcher, line, _ = build(tmp_path)
    await dispatcher.handle(text_event(message_id="m5", mentions_bot=True))
    assert [(c.kind, c.quote_token) for c in line.calls] == [("reply", "quote-m5")]


async def test_a_reply_that_falls_back_to_a_push_still_quotes(tmp_path: Path) -> None:
    dispatcher, line, _ = build(tmp_path, line=FakeLine(reply_accepts=False))
    await dispatcher.handle(text_event(message_id="m5", mentions_bot=True))
    assert [(c.kind, c.quote_token) for c in line.calls] == [
        ("reply", "quote-m5"),
        ("push", "quote-m5"),
    ]


async def test_an_answer_that_raised_is_told_to_the_group_with_the_error_text(
    tmp_path: Path,
) -> None:
    answerer = ScriptedAnswerer()

    async def broken(group_id: str, mention: GroupMessage, **_: Any) -> Answer:
        raise RuntimeError("boom")

    answerer.answer = broken  # type: ignore[method-assign]
    dispatcher, line, group_log = build(tmp_path, answerer)
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.replies == [("reply-token-1", "Sorry, something broke.")]
    assert group_log.list_recent(ALLOWED, 10)[-1].from_bot


async def test_without_an_error_text_a_failed_answer_is_silent(tmp_path: Path) -> None:
    answerer = ScriptedAnswerer()

    async def broken(group_id: str, mention: GroupMessage, **_: Any) -> Answer:
        raise RuntimeError("boom")

    answerer.answer = broken  # type: ignore[method-assign]
    dispatcher, line, _ = build(tmp_path, answerer)
    dispatcher.texts = NoticeTexts()
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.calls == []


async def test_a_person_over_the_hourly_limit_is_told_once_and_not_answered(
    tmp_path: Path,
) -> None:
    answerer = ScriptedAnswerer()
    dispatcher, line, group_log = build(tmp_path, answerer, limiter=MentionLimiter(1))
    for number in range(1, 4):
        await dispatcher.handle(text_event(message_id=f"m{number}", mentions_bot=True))
    assert len(answerer.calls) == 1
    assert [text for _, text in line.replies] == ["Sure.", "Too many asks."]
    assert [c.quote_token for c in line.calls] == ["quote-m1", "quote-m2"]
    # The mentions themselves are still recorded; the notice is not.
    recorded = group_log.list_recent(ALLOWED, 10)
    assert [m.from_bot for m in recorded] == [False, True, False, False]


async def test_each_person_has_their_own_limit(tmp_path: Path) -> None:
    answerer = ScriptedAnswerer()
    dispatcher, _, _ = build(tmp_path, answerer, limiter=MentionLimiter(1))
    await dispatcher.handle(text_event(message_id="m1", mentions_bot=True, user_id="U1"))
    await dispatcher.handle(text_event(message_id="m2", mentions_bot=True, user_id="U2"))
    assert len(answerer.calls) == 2


def waiting(line: FakeLine) -> WaitNotice:
    return WaitNotice(line, PushQuota(line), "One moment.", min_push_left=20)


async def test_a_slow_answer_sends_the_wait_text_by_reply_and_the_answer_by_push(
    tmp_path: Path,
) -> None:
    line = FakeLine(remaining_messages=500)
    dispatcher, line, group_log = build(
        tmp_path, SlowAnswerer(), line=line, wait_notice=waiting(line)
    )
    await dispatcher.handle(text_event(message_id="m5", mentions_bot=True))
    assert line.replies == [("reply-token-1", "One moment.")]
    assert line.pushes == [(ALLOWED, "Sure.")]
    assert line.calls[1].quote_token == "quote-m5"
    # Only the answer is recorded as the bot's message.
    assert [m.text for m in group_log.list_recent(ALLOWED, 10) if m.from_bot] == ["Sure."]


async def test_with_few_pushes_left_there_is_no_wait_text_and_the_answer_is_the_reply(
    tmp_path: Path,
) -> None:
    line = FakeLine(remaining_messages=5)
    dispatcher, line, _ = build(tmp_path, SlowAnswerer(), line=line, wait_notice=waiting(line))
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.replies == [("reply-token-1", "Sure.")] and line.pushes == []


async def test_a_wait_text_that_did_not_use_the_token_leaves_it_for_the_answer(
    tmp_path: Path,
) -> None:
    line = FakeLine(reply_results=[ReplyResult.TOKEN_REFUSED], remaining_messages=500)
    dispatcher, line, _ = build(tmp_path, SlowAnswerer(), line=line, wait_notice=waiting(line))
    await dispatcher.handle(text_event(mentions_bot=True))
    assert [(c.kind, c.text) for c in line.calls] == [
        ("reply", "One moment."),
        ("reply", "Sure."),
    ]


async def test_a_quick_answer_sends_no_wait_text(tmp_path: Path) -> None:
    line = FakeLine()
    dispatcher, line, _ = build(tmp_path, line=line, wait_notice=waiting(line))
    await dispatcher.handle(text_event(mentions_bot=True))
    assert line.replies == [("reply-token-1", "Sure.")] and line.quota_lookups == 0


async def test_joining_an_allowed_group_sends_the_introduction_and_records_it(
    tmp_path: Path,
) -> None:
    dispatcher, line, group_log = build(tmp_path)
    await dispatcher.handle(join_event(ALLOWED))
    assert line.replies == [("t", "Hello, I am the helper.")]
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.from_bot and recorded.text == "Hello, I am the helper."


async def test_joining_a_group_that_is_not_allowed_sends_nothing(tmp_path: Path) -> None:
    dispatcher, line, group_log = build(tmp_path)
    await dispatcher.handle(join_event(OTHER))
    assert line.calls == [] and group_log.list_recent(OTHER, 10) == []


async def test_without_an_introduction_a_join_sends_nothing(tmp_path: Path) -> None:
    dispatcher, line, _ = build(tmp_path)
    dispatcher.texts = NoticeTexts(error="x")
    await dispatcher.handle(join_event(ALLOWED))
    assert line.calls == []


async def test_a_group_the_required_member_is_in_gets_the_introduction(tmp_path: Path) -> None:
    line = FakeLine(members={OPERATOR: True})
    dispatcher, line, _ = build(
        tmp_path,
        line=line,
        required_member_user_id=OPERATOR,
        allow_groups_with_required_member=True,
    )
    await dispatcher.handle(join_event(OTHER))
    assert line.replies == [("t", "Hello, I am the helper.")]


async def test_a_group_without_the_required_member_is_left_without_an_introduction(
    tmp_path: Path,
) -> None:
    line = FakeLine(members={OPERATOR: False})
    dispatcher, line, _ = build(
        tmp_path,
        line=line,
        required_member_user_id=OPERATOR,
        allow_groups_with_required_member=True,
    )
    await dispatcher.handle(join_event(OTHER))
    assert line.calls == [] and line.left_groups == [OTHER]


async def test_a_send_that_failed_alerts_the_operator(tmp_path: Path) -> None:
    line = FakeLine(reply_accepts=False, push_statuses=[500, None])
    notifier = AlertNotifier(line, OPERATOR, clock=lambda: 0.0)
    dispatcher, line, _ = build(tmp_path, line=line, notifier=notifier)
    with pytest.raises(Exception, match="push"):
        await dispatcher.handle(text_event(mentions_bot=True))
    assert line.pushes[-1] == (OPERATOR, ALERT_TEXTS[AlertKind.SEND_FAILED])
