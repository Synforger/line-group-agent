import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent import __main__ as entry
from tests.fakes import raw_config


def write_setup(tmp_path: Path, **overrides: Any) -> Path:
    (tmp_path / "persona.md").write_text("You are a helpful agent.")
    (tmp_path / "anthropic-api-key").write_text("key")
    (tmp_path / "line-channel-secret").write_text("secret")
    (tmp_path / "line-channel-access-token").write_text("token")
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw_config(tmp_path, **overrides)))
    return path


def test_serves_on_loopback_8790_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: calls.append(kw))
    assert entry.main(["--config", str(write_setup(tmp_path))]) == 0
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 8790


def test_start_writes_this_months_spend_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: None)
    entry.main(["--config", str(write_setup(tmp_path))])
    figure = json.loads((tmp_path / "state" / "spend.json").read_text())
    assert figure["spent"] == 0 and figure["limit"] == 1000


def test_a_missing_secret_stops_start_with_status_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_setup(tmp_path)
    (tmp_path / "anthropic-api-key").unlink()
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: pytest.fail("served"))
    assert entry.main(["--config", str(path)]) == 2
    assert "anthropic_api_key_file" in capsys.readouterr().err


def test_runs_from_any_working_directory_with_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "conf"
    folder.mkdir()
    path = write_setup(
        folder,
        persona_file="persona.md",
        state_dir="state",
        anthropic_api_key_file="anthropic-api-key",
        line_channel_secret_file="line-channel-secret",
        line_channel_access_token_file="line-channel-access-token",
    )
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(entry.uvicorn, "run", lambda app, **kw: None)
    assert entry.main(["--config", str(path)]) == 0
    assert (folder / "state" / "spend.json").exists()
    assert list(elsewhere.iterdir()) == []
