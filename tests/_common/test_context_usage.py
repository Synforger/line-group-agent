from datetime import datetime, timedelta, timezone

from line_group_agent._common.context_usage import (
    context_tokens_of,
    is_idle_rollover_due,
    is_rollover_due,
    percent_of,
)
from line_group_agent.config.settings_store import RuntimeSettings

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone(timedelta(hours=9)))
SETTINGS = RuntimeSettings()


def test_the_context_amount_adds_input_cache_read_and_cache_write() -> None:
    usage = {
        "input_tokens": 1,
        "cache_read_input_tokens": 20,
        "cache_creation_input_tokens": 300,
        "output_tokens": 4000,
    }
    assert context_tokens_of(usage) == 321
    assert context_tokens_of({}) == 0


def test_the_percent_is_the_share_of_the_window() -> None:
    assert percent_of(60_000, 100_000) == 60.0
    assert percent_of(5_000, 20_000) == 25.0


def test_a_conversation_is_due_at_the_rollover_percent_and_above() -> None:
    assert not is_rollover_due(59_999, SETTINGS)
    assert is_rollover_due(60_000, SETTINGS)
    assert is_rollover_due(90_000, SETTINGS)


def test_a_quiet_group_is_due_after_the_idle_hours_at_the_idle_percent() -> None:
    quiet_since = NOW - timedelta(hours=6)
    assert is_idle_rollover_due(40_000, quiet_since, NOW, SETTINGS)
    assert not is_idle_rollover_due(39_999, quiet_since, NOW, SETTINGS)
    assert not is_idle_rollover_due(40_000, NOW - timedelta(hours=5, minutes=59), NOW, SETTINGS)
    assert not is_idle_rollover_due(40_000, None, NOW, SETTINGS)
