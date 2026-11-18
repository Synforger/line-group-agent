import anthropic
import httpx
import pytest

from tests.fakes import text_answer
from tests.world import GROUP, build_world

pytestmark = pytest.mark.anyio


class RecordingObserver:
    def __init__(self) -> None:
        self.results: list[bool] = []
        self.spend: list[tuple[float, float]] = []

    async def note_api_result(self, *, is_ok: bool) -> None:
        self.results.append(is_ok)

    async def note_spend(self, spent: float, limit: float) -> None:
        self.spend.append((spent, limit))


async def test_a_good_call_reports_success_and_the_months_spend(tmp_path) -> None:  # type: ignore[no-untyped-def]
    world = build_world(tmp_path, [text_answer("<reply>x</reply>")])
    observer = RecordingObserver()
    world.caller.observer = observer
    await world.caller.create(GROUP, [{"role": "user", "content": "hi"}])
    assert observer.results == [True]
    [(spent, limit)] = observer.spend
    assert spent > 0 and limit == 1000


async def test_a_failed_call_reports_failure_and_no_spend(tmp_path) -> None:  # type: ignore[no-untyped-def]
    world = build_world(tmp_path, [])
    observer = RecordingObserver()
    world.caller.observer = observer
    world.client.messages.error = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    assert await world.caller.create(GROUP, [{"role": "user", "content": "hi"}]) is None
    assert observer.results == [False] and observer.spend == []


async def test_without_an_observer_a_call_works_as_before(tmp_path) -> None:  # type: ignore[no-untyped-def]
    world = build_world(tmp_path, [text_answer("<reply>x</reply>")])
    assert await world.caller.create(GROUP, [{"role": "user", "content": "hi"}]) is not None
