"""The addresses of LINE come from the settings, and are LINE's own when not given."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from line_group_agent.config.agent_config import ConfigError
from line_group_agent.line_api.line_client import API_BASE_URL, DATA_API_BASE_URL, LineClient
from line_group_agent.line_api.login_client import LoginClient
from tests.fakes import make_config

pytestmark = pytest.mark.anyio


def test_the_settings_do_not_name_another_line_unless_asked(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert config.line_api_base_url is None and config.line_data_api_base_url is None


def test_the_settings_may_name_another_line_and_a_trailing_slash_is_dropped(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        line_api_base_url="http://127.0.0.1:9000/",
        line_data_api_base_url="http://127.0.0.1:9001",
    )
    assert config.line_api_base_url == "http://127.0.0.1:9000"
    assert config.line_data_api_base_url == "http://127.0.0.1:9001"


@pytest.mark.parametrize("value", ["127.0.0.1:9000", "ftp://example.com", 7])
def test_an_address_that_is_not_http_is_refused(tmp_path: Path, value: object) -> None:
    with pytest.raises(ConfigError, match="line_api_base_url"):
        make_config(tmp_path, line_api_base_url=value)


def test_the_clients_use_lines_own_addresses_without_settings() -> None:
    assert str(LineClient("token")._http.base_url).rstrip("/") == API_BASE_URL
    assert LineClient("token")._data_base_url == DATA_API_BASE_URL
    assert str(LoginClient()._http.base_url).rstrip("/") == API_BASE_URL


async def test_the_clients_call_the_addresses_they_are_given() -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if request.url.host == "data.test":
            return httpx.Response(200, content=b"bytes", headers={"content-type": "image/png"})
        return httpx.Response(200, json={"groupName": "Friends"})

    line = LineClient("token", base_url="http://api.test", data_base_url="http://data.test")
    line._http = httpx.AsyncClient(
        base_url="http://api.test", transport=httpx.MockTransport(handle)
    )
    await line.get_message_content("77")
    await line.get_group_name("Cg")
    assert seen == [
        "http://data.test/v2/bot/message/77/content",
        "http://api.test/v2/bot/group/Cg/summary",
    ]
    login = LoginClient(base_url="http://api.test")
    assert str(login._http.base_url).rstrip("/") == "http://api.test"
