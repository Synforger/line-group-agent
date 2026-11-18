import json
from typing import Any

import httpx
import pytest

from line_group_agent.line_api.line_client import (
    API_BASE_URL,
    LineApiError,
    LineClient,
    fit_text,
)

pytestmark = pytest.mark.anyio
TOKEN = "channel-access-token"


def client_answering(status: int, body: dict[str, Any] | None = None) -> tuple[LineClient, list]:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body or {})

    http = httpx.AsyncClient(base_url=API_BASE_URL, transport=httpx.MockTransport(handle))
    return LineClient(TOKEN, http_client=http), seen


async def test_reply_posts_one_text_message_with_the_token() -> None:
    line, seen = client_answering(200)
    assert await line.reply("rt", "hello") is True
    request = seen[0]
    assert request.url.path == "/v2/bot/message/reply"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
        "replyToken": "rt",
        "messages": [{"type": "text", "text": "hello"}],
    }


async def test_a_refused_reply_token_returns_false() -> None:
    line, _ = client_answering(400, {"message": "Invalid reply token"})
    assert await line.reply("old", "hello") is False


async def test_another_reply_failure_raises_with_the_status_only() -> None:
    line, _ = client_answering(500)
    with pytest.raises(LineApiError) as error:
        await line.reply("rt", "the text")
    assert error.value.status == 500
    assert "the text" not in str(error.value) and TOKEN not in str(error.value)


async def test_push_goes_to_the_group_with_a_retry_key() -> None:
    line, seen = client_answering(200)
    await line.push("Cgroup", "hello")
    request = seen[0]
    assert request.url.path == "/v2/bot/message/push"
    assert json.loads(request.content)["to"] == "Cgroup"
    assert request.headers["x-line-retry-key"]


async def test_a_failed_push_raises() -> None:
    line, _ = client_answering(429)
    with pytest.raises(LineApiError):
        await line.push("Cgroup", "hello")


async def test_member_name_is_the_display_name() -> None:
    line, seen = client_answering(200, {"displayName": "Aki", "userId": "U1"})
    assert await line.get_member_name("Cgroup", "U1") == "Aki"
    assert seen[0].url.path == "/v2/bot/group/Cgroup/member/U1"


async def test_member_name_is_none_when_line_does_not_give_it() -> None:
    line, _ = client_answering(404)
    assert await line.get_member_name("Cgroup", "U1") is None


def test_text_is_cut_at_5000_utf16_units() -> None:
    assert fit_text("a" * 5000) == "a" * 5000
    assert fit_text("a" * 5001) == "a" * 5000
    emoji = "😀"  # two UTF-16 units
    cut = fit_text(emoji * 2501)
    assert cut == emoji * 2500
