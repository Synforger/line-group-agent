"""The group's member count: asked from LINE, remembered for an hour per group."""

import pytest

from line_group_agent.agent.group_headcount import HEADCOUNT_REMEMBER_SECONDS, GroupHeadcount

pytestmark = pytest.mark.anyio


class Counter:
    """A stand-in for LINE that answers from a list, one count per question."""

    def __init__(self, *counts: int | None) -> None:
        self.counts = list(counts)
        self.asked: list[str] = []

    async def get_member_count(self, group_id: str) -> int | None:
        self.asked.append(group_id)
        return self.counts.pop(0)


class Seconds:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def test_the_count_is_remembered_for_an_hour_per_group() -> None:
    counter, seconds = Counter(4, 5, 7), Seconds()
    headcount = GroupHeadcount(counter, clock=seconds)
    assert await headcount.count_of("Ca") == 4
    assert await headcount.count_of("Cb") == 5
    seconds.now += HEADCOUNT_REMEMBER_SECONDS - 1
    assert await headcount.count_of("Ca") == 4
    assert counter.asked == ["Ca", "Cb"]
    seconds.now += 1
    assert await headcount.count_of("Ca") == 7
    assert counter.asked == ["Ca", "Cb", "Ca"]


async def test_a_count_that_was_not_given_is_none_and_asked_again() -> None:
    counter = Counter(None, 3)
    headcount = GroupHeadcount(counter, clock=Seconds())
    assert await headcount.count_of("Ca") is None
    assert await headcount.count_of("Ca") == 3
    assert counter.asked == ["Ca", "Ca"]
