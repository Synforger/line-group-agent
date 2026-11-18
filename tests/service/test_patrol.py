import asyncio

import pytest

from line_group_agent.service.patrol import Patrol

pytestmark = pytest.mark.anyio


async def test_the_job_runs_at_each_interval_until_stopped() -> None:
    calls: list[int] = []

    async def job() -> None:
        calls.append(len(calls))

    patrol = Patrol(job, 0.01)
    patrol.start()
    await asyncio.sleep(0.1)
    await patrol.stop()
    count = len(calls)
    assert count >= 2
    await asyncio.sleep(0.05)
    assert len(calls) == count


async def test_the_first_round_runs_at_once() -> None:
    calls: list[int] = []

    async def job() -> None:
        calls.append(1)

    patrol = Patrol(job, 60)
    patrol.start()
    await asyncio.sleep(0.02)
    await patrol.stop()
    assert calls == [1]


async def test_a_failed_round_does_not_end_the_patrol() -> None:
    calls: list[int] = []

    async def job() -> None:
        calls.append(1)
        raise RuntimeError("boom")

    patrol = Patrol(job, 0.01)
    patrol.start()
    await asyncio.sleep(0.08)
    await patrol.stop()
    assert len(calls) >= 2
