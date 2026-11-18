import pytest

from line_group_agent.line_api.push_quota import PushQuota
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


async def test_the_answer_is_kept_for_an_hour() -> None:
    line, clock = FakeLine(remaining_messages=50), Clock()
    quota = PushQuota(line, clock=clock)
    assert await quota.remaining() == 50
    line.remaining_messages = 10
    clock.now = 3599
    assert await quota.remaining() == 50
    assert line.quota_lookups == 1
    clock.now = 3600
    assert await quota.remaining() == 10
    assert line.quota_lookups == 2


async def test_a_question_line_did_not_answer_is_asked_again_next_time() -> None:
    line = FakeLine(remaining_messages=None)
    quota = PushQuota(line, clock=Clock())
    assert await quota.remaining() is None
    line.remaining_messages = 30
    assert await quota.remaining() == 30
