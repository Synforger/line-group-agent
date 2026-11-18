"""This month's spend, kept in `<state_dir>/spend.json` for a chat client to show.

Called by the answerer before and after each request. The file is
`{month, spent, limit, currency, updated_at}` and is always rewritten whole: a
temporary file in the same folder, then a rename over the old one.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent._common.atomic_write import write_text_atomically
from line_group_agent.config.agent_config import BudgetConfig

SPENT_DECIMALS = 4


class SpendLedgerError(RuntimeError):
    """The spend file exists but cannot be read; the agent refuses to guess."""


class SpendLedger:
    """Counts this month's spend and refuses spending that would pass the limit."""

    def __init__(
        self,
        path: Path,
        budget: BudgetConfig,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path
        self.budget = budget
        self.limit = budget.monthly_limit
        self._clock = clock or (lambda: datetime.now().astimezone())
        self._month = ""
        self._spent = 0.0

    def open(self) -> None:
        """Load this month's figure (a file of another month counts as 0) and write it."""
        month = self._current_month()
        self._month = month
        self._spent = 0.0
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                saved_month = saved["month"]
                saved_spent = float(saved["spent"])
            except (OSError, ValueError, KeyError, TypeError) as error:
                raise SpendLedgerError(f"cannot read {self.path.name}: {error!r}") from error
            if saved_month == month:
                self._spent = saved_spent
        self._save()

    @property
    def spent(self) -> float:
        """What has been spent this month, in the configured currency."""
        self._roll_month()
        return self._spent

    def can_afford(self, cost: float) -> bool:
        """Return whether spending `cost` more keeps this month within the limit."""
        return self.spent + cost <= self.limit

    def set_limit(self, limit: float) -> None:
        """Change this month's limit (in the configured currency) and rewrite the file."""
        if limit != self.limit:
            self.limit = limit
            self._save()

    def figure(self) -> dict[str, Any]:
        """Return `{month, spent, limit, currency, updated_at}`, as written to the file."""
        self._roll_month()
        return {
            "month": self._month,
            "spent": round(self._spent, SPENT_DECIMALS),
            "limit": self.limit,
            "currency": self.budget.currency,
            "updated_at": self._clock().isoformat(timespec="seconds"),
        }

    def add(self, cost: float) -> None:
        """Count `cost` (in the configured currency) and rewrite the file."""
        self._roll_month()
        self._spent += cost
        self._save()

    def _roll_month(self) -> None:
        month = self._current_month()
        if month != self._month:
            self._month = month
            self._spent = 0.0
            self._save()

    def _current_month(self) -> str:
        return self._clock().strftime("%Y-%m")

    def _save(self) -> None:
        write_text_atomically(self.path, json.dumps(self.figure()))
