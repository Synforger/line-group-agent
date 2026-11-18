"""The table of fields a settings screen offers for the settings file: key, label,
unit, range, step and default.

Listed at the top of the tab list so a chat client can draw its settings screen
without knowing the fields itself. The labels are what a screen shows (Japanese here;
change them to your language); the defaults are those of the settings reader.
"""

from __future__ import annotations

from typing import Any

from line_group_agent.config.settings_store import (
    DEFAULT_CONTEXT_WINDOW_TOKENS,
    DEFAULT_IDLE_HOURS,
    DEFAULT_IDLE_ROLLOVER_PERCENT,
    DEFAULT_ROLLOVER_PERCENT,
)

DEFAULT_MONTHLY_BUDGET_USD = 100

SETTINGS_FIELDS: list[dict[str, Any]] = [
    {
        "key": "monthly_budget_usd",
        "label": "月の予算",
        "unit": "USD",
        "min": 1,
        "max": 1000,
        "step": 1,
        "default": DEFAULT_MONTHLY_BUDGET_USD,
    },
    {
        "key": "context_window_tokens",
        "label": "文脈の窓",
        "unit": "tokens",
        "min": 10_000,
        "max": 200_000,
        "step": 10_000,
        "default": DEFAULT_CONTEXT_WINDOW_TOKENS,
    },
    {
        "key": "rollover_percent",
        "label": "入れ替える文脈の量",
        "unit": "%",
        "min": 10,
        "max": 95,
        "step": 5,
        "default": int(DEFAULT_ROLLOVER_PERCENT),
    },
    {
        "key": "idle_rollover_percent",
        "label": "静かな時に入れ替える文脈の量",
        "unit": "%",
        "min": 5,
        "max": 95,
        "step": 5,
        "default": int(DEFAULT_IDLE_ROLLOVER_PERCENT),
    },
    {
        "key": "idle_hours",
        "label": "静かだと見なす時間",
        "unit": "時間",
        "min": 1,
        "max": 72,
        "step": 1,
        "default": int(DEFAULT_IDLE_HOURS),
    },
]
