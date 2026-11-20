from pathlib import Path

import pytest

from line_group_agent.agent.answerer import Answer
from line_group_agent.events.answer_sender import AnswerSender
from line_group_agent.line_api.line_client import ReplyResult
from line_group_agent.records.group_log import GroupLog, GroupMessage
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
GROUP = "Callowed"
TOKEN = "reply-token-1"
MARKED = "<mention>Aki</mention>さん、割り勘は1200円です"


def log_with_members(tmp_path: Path) -> GroupLog:
    group_log = GroupLog(tmp_path)
    group_log.add(GROUP, GroupMessage("t", "m1", "Uaki", "Aki", "hi"))
    group_log.add(GROUP, GroupMessage("t", "m2", "Uben", "Ben", "hi"))
    return group_log


async def test_the_members_of_the_record_may_be_mentioned(tmp_path: Path) -> None:
    line = FakeLine()
    sender = AnswerSender(line, group_log=log_with_members(tmp_path))
    sent = await sender.send(GROUP, TOKEN, Answer(MARKED))
    [call] = line.calls
    assert call.mentionable == {"Aki": "Uaki", "Ben": "Uben"}
    assert call.text == MARKED
    # The record keeps what the model wrote, so a later deletion finds the reply.
    assert sent is not None and sent.text == MARKED


async def test_a_text_without_a_mark_reads_no_names(tmp_path: Path) -> None:
    line = FakeLine()
    await AnswerSender(line, group_log=log_with_members(tmp_path)).send(
        GROUP, TOKEN, Answer("Hello")
    )
    assert line.calls[0].mentionable is None


async def test_without_a_record_nobody_can_be_mentioned() -> None:
    line = FakeLine()
    await AnswerSender(line).send(GROUP, TOKEN, Answer(MARKED))
    assert line.calls[0].mentionable is None


async def test_a_push_carries_the_mentions_too(tmp_path: Path) -> None:
    line = FakeLine(reply_accepts=False)
    await AnswerSender(line, group_log=log_with_members(tmp_path)).send(
        GROUP, TOKEN, Answer(MARKED)
    )
    assert [(c.kind, c.mentionable is not None) for c in line.calls] == [
        ("reply", True),
        ("push", True),
    ]


async def test_a_reply_line_refuses_is_sent_again_with_the_names_only(tmp_path: Path) -> None:
    line = FakeLine(reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.SENT])
    sender = AnswerSender(line, group_log=log_with_members(tmp_path))
    sent = await sender.send(GROUP, TOKEN, Answer(MARKED))
    assert sent is not None
    assert [(c.kind, c.mentionable is not None) for c in line.calls] == [
        ("reply", True),
        ("reply", False),
    ]


async def test_a_push_line_refuses_is_sent_again_with_the_names_only(tmp_path: Path) -> None:
    line = FakeLine(push_statuses=[400, None])
    sender = AnswerSender(line, group_log=log_with_members(tmp_path))
    assert await sender.send(GROUP, None, Answer(MARKED)) is not None
    assert [(c.kind, c.mentionable is not None) for c in line.calls] == [
        ("push", True),
        ("push", False),
    ]


async def test_a_push_with_a_quote_and_mentions_drops_the_quote_first(tmp_path: Path) -> None:
    line = FakeLine(push_statuses=[400, None])
    sender = AnswerSender(line, group_log=log_with_members(tmp_path))
    await sender.send(GROUP, None, Answer(MARKED), quote_token="q1")
    assert [(c.quote_token, c.mentionable is not None) for c in line.calls] == [
        ("q1", True),
        (None, True),
    ]


async def test_a_push_failure_unlike_a_refusal_is_not_loosened(tmp_path: Path) -> None:
    from line_group_agent.line_api.line_client import LineApiError

    line = FakeLine(push_statuses=[429])
    sender = AnswerSender(line, group_log=log_with_members(tmp_path))
    with pytest.raises(LineApiError):
        await sender.send(GROUP, None, Answer(MARKED))
    assert len(line.calls) == 1
