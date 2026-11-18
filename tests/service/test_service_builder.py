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
