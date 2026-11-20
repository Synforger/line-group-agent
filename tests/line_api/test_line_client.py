import json
from typing import Any

import httpx
import pytest

from line_group_agent.cards.card import Card
from line_group_agent.line_api.line_client import (
    API_BASE_URL,
    UNLIMITED_MESSAGES,
    LineApiError,
    LineClient,
    ReplyResult,
    fit_text,
)
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem

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


async def test_a_reply_and_a_push_put_the_quote_token_on_the_text_message_only() -> None:
    line, seen = client_answering(200)
    await line.reply("rt", "x", CARDS, quote_token="q1")
    await line.push("Cgroup", "x", CARDS, quote_token="q2")
    for request, token in zip(seen, ("q1", "q2"), strict=True):
        text, flex = json.loads(request.content)["messages"]
        assert text["quoteToken"] == token
        assert "quoteToken" not in flex


async def test_without_a_quote_token_the_text_message_has_none() -> None:
    line, seen = client_answering(200)
    await line.reply("rt", "x")
    assert "quoteToken" not in json.loads(seen[0].content)["messages"][0]


def client_routing(routes: dict[str, tuple[int, dict[str, Any]]]) -> LineClient:
    def handle(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(request.url.path, (404, {}))
        return httpx.Response(status, json=body)

    http = httpx.AsyncClient(base_url=API_BASE_URL, transport=httpx.MockTransport(handle))
    return LineClient(TOKEN, http_client=http)


async def test_the_remaining_messages_are_the_quota_less_the_consumption() -> None:
    line = client_routing(
        {
            "/v2/bot/message/quota": (200, {"type": "limited", "value": 200}),
            "/v2/bot/message/quota/consumption": (200, {"totalUsage": 150}),
        }
    )
    assert await line.get_remaining_messages() == 50


async def test_the_remaining_messages_never_go_below_zero() -> None:
    line = client_routing(
        {
            "/v2/bot/message/quota": (200, {"type": "limited", "value": 200}),
            "/v2/bot/message/quota/consumption": (200, {"totalUsage": 230}),
        }
    )
    assert await line.get_remaining_messages() == 0


async def test_an_account_without_a_limit_has_a_very_large_number_left() -> None:
    line = client_routing({"/v2/bot/message/quota": (200, {"type": "none"})})
    assert await line.get_remaining_messages() == UNLIMITED_MESSAGES


async def test_the_remaining_messages_are_none_when_line_does_not_say() -> None:
    assert await client_routing({}).get_remaining_messages() is None
    line = client_routing({"/v2/bot/message/quota": (200, {"type": "limited", "value": 200})})
    assert await line.get_remaining_messages() is None


LOCATION = {
    "type": "location",
    "title": "Gion",
    "address": "Kyoto",
    "latitude": 35.0,
    "longitude": 135.7,
}


async def test_extra_messages_follow_the_text_and_quick_replies_ride_the_last_one() -> None:
    line, seen = client_answering(200)
    extras = [OutgoingExtra(LOCATION, "[位置] Gion")]
    quick = [QuickReplyItem("Yes", "Sora、yes"), QuickReplyItem("No", "Sora、no")]
    await line.reply("rt", "here", extras=extras, quick_replies=quick)
    messages = json.loads(seen[0].content)["messages"]
    assert [m["type"] for m in messages] == ["text", "location"]
    assert "quickReply" not in messages[0]
    assert messages[1]["quickReply"]["items"][0] == {
        "type": "action",
        "action": {"type": "message", "label": "Yes", "text": "Sora、yes"},
    }


async def test_quick_replies_ride_the_text_when_it_is_the_only_message() -> None:
    line, seen = client_answering(200)
    await line.push("Cgroup", "pick one", quick_replies=[QuickReplyItem("A", "A")])
    [message] = json.loads(seen[0].content)["messages"]
    assert message["quickReply"]["items"] == [
        {"type": "action", "action": {"type": "message", "label": "A", "text": "A"}}
    ]


async def test_a_refused_extra_message_is_a_refused_message_not_a_refused_token() -> None:
    line, _ = client_answering(400, {"message": "bad message"})
    extras = [OutgoingExtra(LOCATION, "x")]
    assert await line.reply("rt", "hi", extras=extras) is ReplyResult.MESSAGE_REFUSED


def content_client(status: int, body: bytes, content_type: str) -> LineClient:
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api-data.line.me"
        assert request.url.path == "/v2/bot/message/123/content"
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        return httpx.Response(status, content=body, headers={"content-type": content_type})

    http = httpx.AsyncClient(base_url=API_BASE_URL, transport=httpx.MockTransport(handle))
    return LineClient(TOKEN, http_client=http)


async def test_the_content_of_an_image_is_read_from_the_data_host() -> None:
    line = content_client(200, b"\x89PNG", "image/png; charset=binary")
    assert await line.get_message_content("123") == (b"\x89PNG", "image/png")


async def test_content_that_is_gone_is_none() -> None:
    assert await content_client(404, b"", "text/plain").get_message_content("123") is None


async def test_content_over_the_size_limit_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("line_group_agent.line_api.line_client.MAX_CONTENT_BYTES", 3)
    assert await content_client(200, b"abcd", "image/png").get_message_content("123") is None


async def test_a_mention_mark_of_a_known_name_goes_out_as_a_text_v2_message() -> None:
    line, seen = client_answering(200)
    await line.reply(
        "rt", "<mention>Aki</mention>さん、{ok}", quote_token="q1", mentionable={"Aki": "Uaki"}
    )
    [message] = json.loads(seen[0].content)["messages"]
    assert message == {
        "type": "textV2",
        "text": "{m1}さん、{{ok}}",
        "substitution": {
            "m1": {"type": "mention", "mentionee": {"type": "user", "userId": "Uaki"}}
        },
        "quoteToken": "q1",
    }


async def test_a_push_makes_the_same_text_v2_message() -> None:
    line, seen = client_answering(200)
    await line.push("Cgroup", "<mention>Aki</mention> hi", mentionable={"Aki": "Uaki"})
    [message] = json.loads(seen[0].content)["messages"]
    assert message["type"] == "textV2" and message["text"] == "{m1} hi"


async def test_a_mark_that_cannot_be_a_mention_leaves_the_name_in_a_plain_text() -> None:
    line, seen = client_answering(200)
    await line.reply("rt", "<mention>Cleo</mention> hi {x}", mentionable={"Aki": "Uaki"})
    await line.reply("rt", "<mention>Aki</mention> hi")
    messages = [json.loads(request.content)["messages"][0] for request in seen]
    assert messages == [
        {"type": "text", "text": "Cleo hi {x}"},
        {"type": "text", "text": "Aki hi"},
    ]


async def test_a_message_line_refuses_for_its_mention_is_not_a_refused_token() -> None:
    line, _ = client_answering(400, {"message": "The request body has 1 error(s)"})
    result = await line.reply("rt", "<mention>Aki</mention>", mentionable={"Aki": "Uaki"})
    assert result is ReplyResult.MESSAGE_REFUSED
    assert await line.reply("rt", "<mention>Aki</mention>") is ReplyResult.TOKEN_REFUSED


async def test_a_text_too_long_for_a_text_v2_message_is_sent_plain_and_cut() -> None:
    line, seen = client_answering(200)
    text = "<mention>Aki</mention>" + "あ" * 6000
    await line.reply("rt", text, mentionable={"Aki": "Uaki"})
    [message] = json.loads(seen[0].content)["messages"]
    assert message["type"] == "text" and len(message["text"]) == 5000
