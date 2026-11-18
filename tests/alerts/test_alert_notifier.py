import pytest

from line_group_agent.alerts.alert_notifier import ALERT_TEXTS, AlertKind, AlertNotifier
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
OPERATOR = "Uoperator"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def notifier(
    line: FakeLine, clock: Clock | None = None, user: str | None = OPERATOR
) -> AlertNotifier:
    return AlertNotifier(line, user, clock=clock or Clock())


async def test_three_api_failures_in_a_row_send_one_alert() -> None:
    line = FakeLine()
    alerts = notifier(line)
    for _ in range(2):
        await alerts.note_api_result(is_ok=False)
    assert line.pushes == []
    await alerts.note_api_result(is_ok=False)
    assert line.pushes == [(OPERATOR, ALERT_TEXTS[AlertKind.API_FAILING])]


async def test_a_success_between_failures_resets_the_count() -> None:
    line = FakeLine()
    alerts = notifier(line)
    for is_ok in (False, False, True, False, False):
        await alerts.note_api_result(is_ok=is_ok)
    assert line.pushes == []


async def test_spend_over_eighty_percent_sends_an_alert_and_at_it_does_not() -> None:
    line = FakeLine()
    alerts = notifier(line)
    await alerts.note_spend(80.0, 100.0)
    assert line.pushes == []
    await alerts.note_spend(80.1, 100.0)
    assert line.pushes == [(OPERATOR, ALERT_TEXTS[AlertKind.BUDGET_HIGH])]


async def test_a_limit_of_zero_sends_no_budget_alert() -> None:
    line = FakeLine()
    await notifier(line).note_spend(1.0, 0.0)
    assert line.pushes == []


async def test_a_failed_send_sends_an_alert() -> None:
    line = FakeLine()
    await notifier(line).note_send_failed()
    assert line.pushes == [(OPERATOR, ALERT_TEXTS[AlertKind.SEND_FAILED])]


async def test_the_same_kind_is_sent_once_per_six_hours_and_each_kind_has_its_own() -> None:
    line, clock = FakeLine(), Clock()
    alerts = notifier(line, clock)
    await alerts.note_send_failed()
    clock.now += 6 * 3600 - 1
    await alerts.note_send_failed()
    await alerts.note_spend(90.0, 100.0)
    assert [text for _, text in line.pushes] == [
        ALERT_TEXTS[AlertKind.SEND_FAILED],
        ALERT_TEXTS[AlertKind.BUDGET_HIGH],
    ]
    clock.now += 1
    await alerts.note_send_failed()
    assert len(line.pushes) == 3


async def test_without_a_recipient_nothing_is_sent() -> None:
    line = FakeLine()
    await notifier(line, user=None).note_send_failed()
    assert line.pushes == []


async def test_an_alert_that_could_not_be_sent_is_tried_again_at_the_next_event() -> None:
    line = FakeLine(push_statuses=[500, None])
    alerts = notifier(line)
    await alerts.note_send_failed()
    await alerts.note_send_failed()
    assert len(line.pushes) == 2
