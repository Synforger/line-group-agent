import json
from typing import Any

import httpx
import pytest

from line_group_agent.cards.card import Card
from line_group_agent.line_api.line_client import (
    API_BASE_URL,
    LineApiError,
    LineClient,
    ReplyResult,
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
    assert await line.reply("rt", "hello") is ReplyResult.SENT
    request = seen[0]
    assert request.url.path == "/v2/bot/message/reply"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {
        "replyToken": "rt",
        "messages": [{"type": "text", "text": "hello"}],
    }


async def test_a_refused_reply_token_returns_false() -> None:
    line, _ = client_answering(400, {"message": "Invalid reply token"})
    assert await line.reply("old", "hello") is ReplyResult.TOKEN_REFUSED


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


CARDS = [
    Card("Gion Inn", "Near the station", "https://example.com/1", image_url="https://e.com/1.jpg")
]


async def test_a_reply_with_cards_sends_the_text_first_and_one_flex_message_after() -> None:
    line, seen = client_answering(200)
    assert await line.reply("rt", "Here are two.", CARDS) is ReplyResult.SENT
    messages = json.loads(seen[0].content)["messages"]
    assert [m["type"] for m in messages] == ["text", "flex"]
    assert messages[0]["text"] == "Here are two."
    assert messages[1]["contents"]["type"] == "carousel"
    assert messages[1]["contents"]["contents"][0].get("hero") is not None


async def test_cards_alone_are_one_flex_message_and_text_alone_one_text_message() -> None:
    line, seen = client_answering(200)
    await line.reply("rt", None, CARDS)
    await line.push("Cgroup", "only text")
    assert [m["type"] for m in json.loads(seen[0].content)["messages"]] == ["flex"]
    assert [m["type"] for m in json.loads(seen[1].content)["messages"]] == ["text"]


async def test_without_images_the_cards_carry_no_picture() -> None:
    line, seen = client_answering(200)
    await line.reply("rt", "x", CARDS, with_images=False)
    flex = json.loads(seen[0].content)["messages"][1]
    assert "hero" not in flex["contents"]["contents"][0]


async def test_a_push_with_cards_sends_both_messages() -> None:
    line, seen = client_answering(200)
    await line.push("Cgroup", "x", CARDS)
    body = json.loads(seen[0].content)
    assert body["to"] == "Cgroup"
    assert [m["type"] for m in body["messages"]] == ["text", "flex"]


async def test_a_400_about_the_reply_token_is_a_refused_token_even_with_cards() -> None:
    line, _ = client_answering(400, {"message": "Invalid reply token"})
    assert await line.reply("old", "x", CARDS) is ReplyResult.TOKEN_REFUSED


async def test_a_400_about_the_message_shape_is_a_refused_message_when_cards_were_sent() -> None:
    body = {
        "message": "The request body has 1 error(s)",
        "details": [{"message": "must be valid URL", "property": "messages[1].contents"}],
    }
    line, _ = client_answering(400, body)
    assert await line.reply("rt", "x", CARDS) is ReplyResult.MESSAGE_REFUSED


async def test_a_400_without_a_readable_body_counts_as_a_refused_message_with_cards() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, content=b"not json")

    http = httpx.AsyncClient(base_url=API_BASE_URL, transport=httpx.MockTransport(handle))
    line = LineClient(TOKEN, http_client=http)
    assert await line.reply("rt", "x", CARDS) is ReplyResult.MESSAGE_REFUSED


async def test_a_400_on_a_text_only_reply_is_still_a_refused_token() -> None:
    line, _ = client_answering(400, {"message": "The request body has 1 error(s)"})
    assert await line.reply("rt", "x") is ReplyResult.TOKEN_REFUSED


async def test_a_failed_push_with_cards_carries_the_status_and_no_body() -> None:
    line, _ = client_answering(400, {"message": "The request body has 1 error(s)"})
    with pytest.raises(LineApiError) as error:
        await line.push("Cgroup", "secret words", CARDS)
    assert error.value.status == 400
    assert "secret words" not in str(error.value) and "example.com" not in str(error.value)


@pytest.mark.parametrize(("status", "expected"), [(200, True), (404, False), (500, None)])
async def test_is_member_reads_the_member_profile_status(
    status: int, expected: bool | None
) -> None:
    line, seen = client_answering(status, {"displayName": "Aki"})
    assert await line.is_member("Cg", "U1") is expected
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/v2/bot/group/Cg/member/U1"


async def test_leave_group_posts_to_the_leave_endpoint() -> None:
    line, seen = client_answering(200)
    await line.leave_group("Cg")
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v2/bot/group/Cg/leave"


async def test_a_failed_leave_raises_with_the_status() -> None:
    line, _ = client_answering(403)
    with pytest.raises(LineApiError) as raised:
        await line.leave_group("Cg")
    assert raised.value.status == 403


async def test_group_name_is_read_from_the_group_summary() -> None:
    line, seen = client_answering(200, {"groupId": "Cg", "groupName": "Trip friends"})
    assert await line.get_group_name("Cg") == "Trip friends"
    assert seen[0].method == "GET" and seen[0].url.path == "/v2/bot/group/Cg/summary"


async def test_group_name_is_none_when_line_does_not_give_it() -> None:
    line, _ = client_answering(403)
    assert await line.get_group_name("Cg") is None
    line, _ = client_answering(200, {"groupId": "Cg"})
    assert await line.get_group_name("Cg") is None
