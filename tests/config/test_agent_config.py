import json
from pathlib import Path

import pytest

from line_group_agent.config.agent_config import (
    ConfigError,
    load_config,
    load_secrets,
    parse_config,
)
from tests.fakes import make_config, raw_config


def test_defaults_match_the_agreed_receiving_point(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.host == "127.0.0.1"
    assert config.port == 8790
    assert config.max_body_bytes == 1024 * 1024
    assert config.model == "claude-haiku-5-5"
    assert config.max_tokens == 1024
    assert config.recent_message_count == 30
    assert config.max_tool_rounds == 4
    assert config.history_search_limit == 20
    assert config.redelivered_answer_window_seconds == 600
    assert config.web_search is not None and config.web_search.max_uses == 3
    assert config.budget.currency == "JPY"
    assert config.budget.exhausted_text == "This month's budget is used up."
    assert config.allowed_group_ids == frozenset({"Callowed"})


def test_every_default_can_be_set(tmp_path: Path) -> None:
    config = make_config(
        tmp_path, host="0.0.0.0", port=9000, max_body_bytes=10, recent_message_count=5
    )
    assert (config.host, config.port, config.max_body_bytes) == ("0.0.0.0", 9000, 10)
    assert config.recent_message_count == 5


def test_a_web_tool_set_to_null_is_off(tmp_path: Path) -> None:
    config = make_config(tmp_path, web_fetch=None)
    assert config.web_fetch is None


@pytest.mark.parametrize("key", ["persona_file", "state_dir", "tab_name", "prices_usd", "budget"])
def test_required_settings_are_required(tmp_path: Path, key: str) -> None:
    raw = raw_config(tmp_path)
    del raw[key]
    with pytest.raises(ConfigError, match=key):
        parse_config(raw, tmp_path)


def test_prices_have_no_default(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    del raw["prices_usd"]["output_per_mtok"]
    with pytest.raises(ConfigError, match="output_per_mtok"):
        parse_config(raw, tmp_path)


@pytest.mark.parametrize("name", ["Group", "a b", "../x", ""])
def test_tab_name_is_checked(tmp_path: Path, name: str) -> None:
    with pytest.raises(ConfigError):
        make_config(tmp_path, tab_name=name)


def test_a_wrong_kind_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="port"):
        make_config(tmp_path, port="8790")
    with pytest.raises(ConfigError, match="port"):
        make_config(tmp_path, port=True)


def test_load_config_reads_a_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw_config(tmp_path)))
    assert load_config(path).tab_name == "group-test"


def test_load_config_names_a_broken_file(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("{")
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(path)


def test_secrets_are_read_from_their_files(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.anthropic_api_key_file.write_text("key-value\n")
    config.line_channel_secret_file.write_text("secret-value")
    config.line_channel_access_token_file.write_text("token-value")
    secrets = load_secrets(config)
    assert secrets.anthropic_api_key == "key-value"
    assert secrets.line_channel_secret == "secret-value"
    assert secrets.line_channel_access_token == "token-value"


def test_an_empty_secret_file_is_refused_without_showing_content(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.anthropic_api_key_file.write_text("key-value")
    config.line_channel_secret_file.write_text("  \n")
    config.line_channel_access_token_file.write_text("token-value")
    with pytest.raises(ConfigError) as error:
        load_secrets(config)
    assert "line_channel_secret_file" in str(error.value)
    assert "key-value" not in str(error.value)


def test_relative_paths_are_taken_from_the_config_files_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "conf"
    folder.mkdir()
    raw = raw_config(tmp_path, persona_file="persona.md", state_dir="../state")
    raw["anthropic_api_key_file"] = "/absolute/key"
    (folder / "config.json").write_text(json.dumps(raw))
    monkeypatch.chdir(tmp_path)
    config = load_config(Path("conf/config.json"))
    assert config.persona_file == folder.resolve() / "persona.md"
    assert config.state_dir == folder.resolve() / "../state"
    assert config.anthropic_api_key_file == Path("/absolute/key")


def test_a_tilde_is_not_expanded_from_the_environment(tmp_path: Path) -> None:
    config = make_config(tmp_path, persona_file="~/persona.md")
    assert config.persona_file == tmp_path / "~" / "persona.md"
