import logging
from typing import Any

import httpx
import pytest

from line_group_agent.line_api.line_client import API_BASE_URL, LineApiError
from line_group_agent.line_api.login_client import LoginClient

pytestmark = pytest.mark.anyio
ID_TOKEN = "an-id-token"


def client_answering(
    status: int, body: Any = None, *, content: bytes | None = None
) -> tuple[LoginClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if content is not None:
            return httpx.Response(status, content=content)
        return httpx.Response(status, json=body if body is not None else {})

    http = httpx.AsyncClient(base_url=API_BASE_URL, transport=httpx.MockTransport(handle))
    return LoginClient(http_client=http), seen


async def test_the_token_and_the_channel_are_posted_as_a_form_to_the_verify_address() -> None:
    login, seen = client_answering(200, {"sub": "U1", "aud": "123"})
    assert await login.verify_id_token(ID_TOKEN, "123") == {"sub": "U1", "aud": "123"}
    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.line.me/oauth2/v2.1/verify"
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    assert request.content == b"id_token=an-id-token&client_id=123"
    assert "authorization" not in request.headers


async def test_a_token_line_refuses_gives_none() -> None:
    login, _ = client_answering(400, {"error": "invalid_request"})
    assert await login.verify_id_token(ID_TOKEN, "123") is None


@pytest.mark.parametrize("content", [b"not json", b"[1, 2]"])
async def test_an_answer_that_is_not_claims_gives_none(content: bytes) -> None:
    login, _ = client_answering(200, content=content)
    assert await login.verify_id_token(ID_TOKEN, "123") is None


@pytest.mark.parametrize("status", [401, 429, 500, 503])
async def test_another_status_raises_with_the_status_only(
    status: int, caplog: pytest.LogCaptureFixture
) -> None:
    login, _ = client_answering(status)
    with caplog.at_level(logging.DEBUG), pytest.raises(LineApiError) as error:
        await login.verify_id_token(ID_TOKEN, "123")
    assert error.value.status == status
    assert ID_TOKEN not in str(error.value) and ID_TOKEN not in caplog.text


async def test_no_connection_raises_with_status_zero() -> None:
    def fail(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    http = httpx.AsyncClient(base_url=API_BASE_URL, transport=httpx.MockTransport(fail))
    with pytest.raises(LineApiError) as error:
        await LoginClient(http_client=http).verify_id_token(ID_TOKEN, "123")
    assert error.value.status == 0
    assert ID_TOKEN not in str(error.value)
