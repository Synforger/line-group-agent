from pathlib import Path

import pytest

from line_group_agent.service.service_builder import ANTHROPIC_BASE_URL, create_anthropic_client


@pytest.fixture
def hostile_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "key-from-environment")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-from-environment")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9/elsewhere")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:9")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:9")


@pytest.mark.usefixtures("hostile_environment")
def test_the_api_client_takes_nothing_from_the_environment() -> None:
    client = create_anthropic_client("key-from-file")
    assert client.api_key == "key-from-file"
    assert client.auth_token is None
    assert str(client.base_url).rstrip("/") == ANTHROPIC_BASE_URL
    assert client.open_telemetry["traces"]["enabled"] is False
    assert client._client._mounts == {}


def test_the_service_builds_its_parts_and_writes_the_tab_list(tmp_path: Path) -> None:
    import json

    from line_group_agent.service.service_builder import build_app
    from tests.fakes import make_config

    config = make_config(tmp_path)
    config.persona_file.write_text("You are a helper.")
    for secret_file in (
        config.anthropic_api_key_file,
        config.line_channel_secret_file,
        config.line_channel_access_token_file,
    ):
        secret_file.write_text("secret\n")
    build_app(config)
    tabs = json.loads(config.tabs_file.read_text())
    assert [tab["name"] for tab in tabs["tabs"]] == ["g-callowed"]


def build_with(tmp_path: Path, **overrides: object) -> None:
    from line_group_agent.service.service_builder import build_app
    from tests.fakes import make_config

    config = make_config(tmp_path, **overrides)
    config.persona_file.write_text("You are a helper.")
    for secret_file in (
        config.anthropic_api_key_file,
        config.line_channel_secret_file,
        config.line_channel_access_token_file,
    ):
        secret_file.write_text("secret\n")
    build_app(config)


def test_an_intro_file_that_cannot_be_read_stops_the_start(tmp_path: Path) -> None:
    from line_group_agent.config.agent_config import ConfigError

    with pytest.raises(ConfigError, match="intro_file"):
        build_with(tmp_path, intro_file="missing.txt")


def test_an_intro_file_that_can_be_read_lets_the_service_start(tmp_path: Path) -> None:
    (tmp_path / "intro.txt").write_text("Hello.\n")
    build_with(tmp_path, intro_file="intro.txt")


class SpyFinder:
    """Counts how many card image finders the service builder made."""

    made = 0

    def __init__(self) -> None:
        SpyFinder.made += 1

    async def close(self) -> None:
        return None


@pytest.mark.parametrize(("lookup", "made"), [(True, 1), (False, 0)])
def test_the_card_image_finder_is_made_only_when_the_lookup_is_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lookup: bool, made: int
) -> None:
    SpyFinder.made = 0
    monkeypatch.setattr("line_group_agent.service.service_builder.CardImageFinder", SpyFinder)
    build_with(tmp_path, card_image_lookup=lookup)
    assert SpyFinder.made == made


def test_the_lookup_is_on_by_default(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    SpyFinder.made = 0
    monkeypatch.setattr("line_group_agent.service.service_builder.CardImageFinder", SpyFinder)
    build_with(tmp_path)
    assert SpyFinder.made == 1
