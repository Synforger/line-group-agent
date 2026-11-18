"""Tell the operator, by one short push, when the agent cannot do its job.

Called by the model caller (after each API call and each cost) and by the answer
sender (when LINE refuses a send). Three kinds of alert: the API failed several times
in a row, the whole month's spend passed most of its limit, and a send to LINE failed.
The same kind is sent at most once per cooldown. Without a recipient nothing is sent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from enum import StrEnum
from typing import Protocol

from line_group_agent.cards.card import Card
from line_group_agent.line_api.line_client import LineApiError

logger = logging.getLogger(__name__)

API_FAILURE_STREAK = 3
BUDGET_ALERT_RATIO = 0.8
COOLDOWN_SECONDS = 6 * 60 * 60


class AlertKind(StrEnum):
    """What an alert is about; each kind has its own text and its own cooldown."""

    API_FAILING = "api_failing"
    BUDGET_HIGH = "budget_high"
    SEND_FAILED = "send_failed"


ALERT_TEXTS = {
    AlertKind.API_FAILING: f"Alert: the Claude API failed {API_FAILURE_STREAK} times in a row.",
    AlertKind.BUDGET_HIGH: "Alert: this month's spend passed 80% of the limit.",
    AlertKind.SEND_FAILED: "Alert: sending a message to LINE failed.",
}


class AlertLine(Protocol):
    """What the notifier needs from the LINE client: a push to one user."""

    async def push(self, to: str, text: str | None, cards: Sequence[Card] = ()) -> None: ...


class AlertNotifier:
    """Sends the operator an alert, at most once per kind per cooldown."""

    def __init__(
        self,
        line: AlertLine,
        user_id: str | None,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.line = line
        self.user_id = user_id
        self._clock = clock
        self._failure_streak = 0
        self._last_sent: dict[AlertKind, float] = {}

    async def note_api_result(self, *, is_ok: bool) -> None:
        """Count one API call; alert when failures reach the streak."""
        self._failure_streak = 0 if is_ok else self._failure_streak + 1
        if self._failure_streak >= API_FAILURE_STREAK:
            await self._alert(AlertKind.API_FAILING)

    async def note_spend(self, spent: float, limit: float) -> None:
        """Alert when the whole month's spend is over most of its limit."""
        if limit > 0 and spent > limit * BUDGET_ALERT_RATIO:
            await self._alert(AlertKind.BUDGET_HIGH)

    async def note_send_failed(self) -> None:
        """Alert that LINE refused or lost a message the agent sent."""
        await self._alert(AlertKind.SEND_FAILED)

    async def _alert(self, kind: AlertKind) -> None:
        if self.user_id is None:
            return
        now = self._clock()
        last = self._last_sent.get(kind)
        if last is not None and now - last < COOLDOWN_SECONDS:
            return
        try:
            await self.line.push(self.user_id, ALERT_TEXTS[kind])
        except LineApiError as error:
            logger.warning("alert: could not send %s (status %d)", kind, error.status)
            return
        self._last_sent[kind] = now
