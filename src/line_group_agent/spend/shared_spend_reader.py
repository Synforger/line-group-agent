"""This month's spend of the other programs that share the API key, read from their files.

Called by the spend books on every overall check. Each file is `{month, spent, limit,
currency, updated_at}`, the same shape as this agent's own `spend.json`, and is written by
the other program, so it is read again each time and never remembered.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent.config.agent_config import BudgetConfig

logger = logging.getLogger(__name__)


class SharedSpendReader:
    """Adds up the other programs' figures for this month in the configured currency."""

    def __init__(
        self,
        budget: BudgetConfig,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.budget = budget
        self._clock = clock or (lambda: datetime.now().astimezone())

    def total(self) -> float | None:
        """Return what the other programs spent this month, or `None` when a file cannot be used.

        A missing file and a file of another month count as 0. A file in another currency, or
        one that is unreadable, lacks a field or holds a `spent` that is not a plain number,
        gives no answer at all, because the amount it stands for is not known.
        """
        month = self._clock().strftime("%Y-%m")
        total = 0.0
        for path in self.budget.shared_spend_files:
            spent = self._spent_in(path, month)
            if spent is None:
                return None
            total += spent
        return total

    def _spent_in(self, path: Path, month: str) -> float | None:
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return 0.0
        except (OSError, ValueError) as error:
            return self._refuse(path, f"cannot read it: {error!r}")
        problem = self._problem_with(saved)
        if problem is not None:
            return self._refuse(path, problem)
        if saved["month"] != month:
            return 0.0
        if saved["currency"] != self.budget.currency:
            return self._refuse(
                path, f"currency {saved['currency']!r} is not {self.budget.currency!r}"
            )
        return float(saved["spent"])

    def _problem_with(self, saved: Any) -> str | None:
        if not isinstance(saved, dict):
            return "it does not hold an object"
        for key in ("month", "spent", "currency"):
            if key not in saved:
                return f"it has no {key!r}"
        spent = saved["spent"]
        if (
            isinstance(spent, bool)
            or not isinstance(spent, int | float)
            or not math.isfinite(spent)
            or spent < 0
        ):
            return f"spent {spent!r} is not a number of 0 or more"
        return None

    def _refuse(self, path: Path, reason: str) -> None:
        logger.warning(
            "shared spend file %s cannot be used, so no spending is allowed: %s", path.name, reason
        )
        return None
