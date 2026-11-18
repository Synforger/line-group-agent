import pytest

from line_group_agent.events.wait_notice import WaitNotice
from line_group_agent.line_api.line_client import LineApiError, ReplyResult
from line_group_agent.line_api.push_quota import PushQuota
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio


def notice(line: FakeLine, text: str = "One moment.", min_push_left: int = 20) -> WaitNotice:
    return WaitNotice(line, PushQuota(line), text, min_push_left=min_push_left)


async def test_the_text_is_sent_through_the_reply_token_when_pushes_are_to_spare() -> None:
    line = FakeLine(remaining_messages=500)
    assert await notice(line).send("rt") is True
    assert line.replies == [("rt", "One moment.")]


async def test_it_is_not_sent_when_fewer_pushes_are_left_than_the_minimum() -> None:
    line = FakeLine(remaining_messages=19)
    assert await notice(line).send("rt") is False
    assert line.calls == []


async def test_exactly_the_minimum_is_enough() -> None:
    line = FakeLine(remaining_messages=20)
    assert await notice(line).send("rt") is True


async def test_it_is_not_sent_when_line_does_not_say_how_many_are_left() -> None:
    line = FakeLine(remaining_messages=None)
    assert await notice(line).send("rt") is False
    assert line.calls == []


async def test_it_is_not_sent_without_a_text_or_a_token() -> None:
    line = FakeLine()
    assert await notice(line, text="").send("rt") is False
    assert await notice(line).send(None) is False
    assert line.calls == []


async def test_a_refused_token_means_the_notice_did_not_use_it() -> None:
    line = FakeLine(reply_accepts=False)
    assert await notice(line).send("rt") is False


async def test_a_failing_reply_means_the_notice_did_not_use_it() -> None:
    class Failing(FakeLine):
        async def reply(self, *args: object, **kwargs: object) -> ReplyResult:
            raise LineApiError("reply", 500)

    assert await notice(Failing()).send("rt") is False
