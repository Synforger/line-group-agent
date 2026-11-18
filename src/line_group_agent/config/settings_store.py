"""The settings a chat client's settings screen writes, read again whenever the file
changes.

Called at every event and every patrol. A missing file or a missing field means the
default; a file that cannot be used leaves the previous values in place and logs one
line. Money, the context window and the rollover thresholds live here so they can be
changed without restarting the agent.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_WINDOW_TOKENS = 100_000
DEFAULT_ROLLOVER_PERCENT = 60.0
DEFAULT_IDLE_ROLLOVER_PERCENT = 40.0
DEFAULT_IDLE_HOURS = 6.0
MAX_PERCENT = 100.0


class SettingsError(ValueError):
    """The settings file holds a value of the wrong kind or out of range."""


@dataclass(frozen=True)
class RuntimeSettings:
    """The values the settings file can change.

    `monthly_budget_usd` is `None` when the file does not give one; the budget of the
    configuration file then applies.
    """

    monthly_budget_usd: float | None = None
    context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS
    rollover_percent: float = DEFAULT_ROLLOVER_PERCENT
    idle_rollover_percent: float = DEFAULT_IDLE_ROLLOVER_PERCENT
    idle_hours: float = DEFAULT_IDLE_HOURS


class SettingsStore:
    """Holds the current settings and re-reads the file when its modification changes."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._values = RuntimeSettings()
        self._signature: tuple[int, int] | None = None
        self._is_loaded = False

    def current(self) -> RuntimeSettings:
        """Return the settings, reading the file again first if it changed."""
        if self.path is None:
            return self._values
        signature = self._signature_of_file()
        if self._is_loaded and signature == self._signature:
            return self._values
        self._is_loaded = True
        self._signature = signature
        if signature is None:
            self._values = RuntimeSettings()
            return self._values
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self._values = parse_settings(raw)
        except (OSError, ValueError) as error:
            logger.warning(
                "settings: cannot use %s (%s); keeping the previous values",
                self.path.name,
                type(error).__name__,
            )
        return self._values

    def _signature_of_file(self) -> tuple[int, int] | None:
        assert self.path is not None
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)


def parse_settings(raw: Any) -> RuntimeSettings:
    """Build settings from parsed JSON; a field that is missing takes its default."""
    if not isinstance(raw, dict):
        raise SettingsError("the settings file must hold one JSON object")
    defaults = RuntimeSettings()
    budget = raw.get("monthly_budget_usd")
    return RuntimeSettings(
        monthly_budget_usd=None if budget is None else _number(raw, "monthly_budget_usd", 0.0),
        context_window_tokens=_whole_number(
            raw, "context_window_tokens", defaults.context_window_tokens
        ),
        rollover_percent=_percent(raw, "rollover_percent", defaults.rollover_percent),
        idle_rollover_percent=_percent(
            raw, "idle_rollover_percent", defaults.idle_rollover_percent
        ),
        idle_hours=_number(raw, "idle_hours", defaults.idle_hours, positive=True),
    )


def _number(raw: dict[str, Any], key: str, default: float, *, positive: bool = False) -> float:
    value = raw.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SettingsError(f"{key} must be a number")
    if value < 0 or (positive and value == 0):
        raise SettingsError(f"{key} is out of range")
    return float(value)


def _whole_number(raw: dict[str, Any], key: str, default: int) -> int:
    value = raw.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SettingsError(f"{key} must be a positive whole number")
    return value


def _percent(raw: dict[str, Any], key: str, default: float) -> float:
    value = _number(raw, key, default, positive=True)
    if value > MAX_PERCENT:
        raise SettingsError(f"{key} is out of range")
    return value
