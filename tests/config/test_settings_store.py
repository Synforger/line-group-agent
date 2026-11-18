import json
import logging
import os
from pathlib import Path

import pytest

from line_group_agent.config.settings_store import (
    RuntimeSettings,
    SettingsError,
    SettingsStore,
    parse_settings,
)


def write(path: Path, content: object) -> None:
    path.write_text(json.dumps(content))
    stat = path.stat()
    # A file written twice within the clock's resolution must still look changed.
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000 * write.count))
    write.count += 1


write.count = 1


def test_without_a_file_the_defaults_apply(tmp_path: Path) -> None:
    assert SettingsStore(tmp_path / "none.json").current() == RuntimeSettings()
    assert SettingsStore(None).current() == RuntimeSettings()
    defaults = RuntimeSettings()
    assert (defaults.context_window_tokens, defaults.rollover_percent) == (100_000, 60.0)
    assert (defaults.idle_rollover_percent, defaults.idle_hours) == (40.0, 6.0)
    assert defaults.monthly_budget_usd is None


def test_a_missing_field_takes_its_default(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    write(path, {"monthly_budget_usd": 100, "rollover_percent": 70})
    settings = SettingsStore(path).current()
    assert settings.monthly_budget_usd == 100
    assert settings.rollover_percent == 70
    assert settings.idle_hours == 6.0


def test_the_file_is_read_again_when_it_changes(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    write(path, {"idle_hours": 2})
    store = SettingsStore(path)
    assert store.current().idle_hours == 2
    write(path, {"idle_hours": 9})
    assert store.current().idle_hours == 9


def test_a_broken_file_keeps_the_previous_values_and_logs_one_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "s.json"
    write(path, {"idle_hours": 2})
    store = SettingsStore(path)
    store.current()
    path.write_text("{not json")
    os.utime(path, ns=(0, 5_000_000_000_000_000_000))
    with caplog.at_level(logging.WARNING):
        assert store.current().idle_hours == 2
        assert store.current().idle_hours == 2
    assert len([r for r in caplog.records if "settings:" in r.message]) == 1
    assert "not json" not in caplog.text


def test_a_removed_file_goes_back_to_the_defaults(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    write(path, {"idle_hours": 2})
    store = SettingsStore(path)
    store.current()
    path.unlink()
    assert store.current() == RuntimeSettings()


@pytest.mark.parametrize(
    "raw",
    [
        [],
        {"monthly_budget_usd": "100"},
        {"monthly_budget_usd": -1},
        {"context_window_tokens": 1.5},
        {"context_window_tokens": 0},
        {"rollover_percent": 101},
        {"idle_rollover_percent": 0},
        {"idle_hours": True},
        {"idle_hours": 0},
    ],
)
def test_values_of_the_wrong_kind_or_range_are_refused(raw: object) -> None:
    with pytest.raises(SettingsError):
        parse_settings(raw)
