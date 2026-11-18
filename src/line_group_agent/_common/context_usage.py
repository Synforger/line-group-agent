"""How much of the context window a conversation fills, and when to roll it over.

Pure calculations over an answer's `usage` and the settings; called by the
conversation state, the rollover and the tab list.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from line_group_agent.config.settings_store import RuntimeSettings

PERCENT = 100.0


def context_tokens_of(usage: dict[str, Any]) -> int:
    """Return the context amount of an answer: input, cache read and cache write tokens."""
    return sum(
        _count(usage, key)
        for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    )


def percent_of(context_tokens: int, window_tokens: int) -> float:
    """Return the share of the window the context fills, in percent."""
    return context_tokens / window_tokens * PERCENT


def is_rollover_due(context_tokens: int, settings: RuntimeSettings) -> bool:
    """Return whether an answered conversation is full enough to be rolled over."""
    return percent_of(context_tokens, settings.context_window_tokens) >= settings.rollover_percent


def is_idle_rollover_due(
    context_tokens: int, last_activity_at: datetime | None, now: datetime, settings: RuntimeSettings
) -> bool:
    """Return whether a quiet group's conversation should be rolled over: nothing was
    said for `idle_hours` and the context is at least `idle_rollover_percent` full."""
    if last_activity_at is None:
        return False
    is_quiet = now - last_activity_at >= timedelta(hours=settings.idle_hours)
    percent = percent_of(context_tokens, settings.context_window_tokens)
    return is_quiet and percent >= settings.idle_rollover_percent


def _count(section: dict[str, Any], key: str) -> int:
    value = section.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
