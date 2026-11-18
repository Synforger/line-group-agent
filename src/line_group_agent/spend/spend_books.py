"""All the money counters of the agent: the overall month and one month per group.

Called by the model caller (to check and add a cost), the tab list (to show a group's
figure) and the settings reader's users. The overall limit comes from the settings
file when it gives one, else from the configuration; each group may spend the overall
limit divided by the number of groups.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from line_group_agent.config.agent_config import BudgetConfig
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.spend.spend_ledger import SpendLedger

LIMIT_DECIMALS = 4


class SpendBooks:
    """The overall spend ledger and a lazily opened ledger for each group."""

    def __init__(
        self,
        overall: SpendLedger,
        state_dir: Path,
        budget: BudgetConfig,
        settings: SettingsStore,
        group_count: Callable[[], int],
    ) -> None:
        self.overall = overall
        self.state_dir = state_dir
        self.budget = budget
        self.settings = settings
        self.group_count = group_count
        self._groups: dict[str, SpendLedger] = {}

    def can_afford(self, group_id: str, cost: float) -> bool:
        """Return whether both the overall month and the group's month can take `cost`."""
        self._sync_limits()
        return self.overall.can_afford(cost) and self._group(group_id).can_afford(cost)

    def add(self, group_id: str, cost: float) -> None:
        """Count `cost` against the overall month and the group's month."""
        self.overall.add(cost)
        self._group(group_id).add(cost)

    def group_figure(self, group_id: str) -> dict[str, Any]:
        """Return the group's month as `{month, spent, limit, currency}`."""
        self._sync_limits()
        figure = self._group(group_id).figure()
        return {key: figure[key] for key in ("month", "spent", "limit", "currency")}

    def overall_limit(self) -> float:
        """Return the overall monthly limit in the configured currency."""
        budget_usd = self.settings.current().monthly_budget_usd
        if budget_usd is None:
            return self.budget.monthly_limit
        return budget_usd * self.budget.currency_per_usd

    def _sync_limits(self) -> None:
        limit = self.overall_limit()
        self.overall.set_limit(limit)
        group_limit = self._group_limit_of(limit)
        for ledger in self._groups.values():
            ledger.set_limit(group_limit)

    def _group(self, group_id: str) -> SpendLedger:
        if group_id not in self._groups:
            ledger = SpendLedger(self.state_dir / "groups" / group_id / "spend.json", self.budget)
            ledger.open()
            ledger.set_limit(self._group_limit_of(self.overall_limit()))
            self._groups[group_id] = ledger
        return self._groups[group_id]

    def _group_limit_of(self, overall_limit: float) -> float:
        return round(overall_limit / max(1, self.group_count()), LIMIT_DECIMALS)
