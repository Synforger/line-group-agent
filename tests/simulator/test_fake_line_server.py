"""The stand-in LINE is exercised with the bot's own LINE clients, so what the bot calls is
what is checked."""

from __future__ import annotations

import httpx
import pytest

from line_group_agent.cards.card import Card
from line_group_agent.line_api.line_client import LineApiError, LineClient, ReplyResult
from line_group_agent.line_api.login_client import LoginClient
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem
from line_group_agent.simulator.fake_line_server import FakeLineServer
from line_group_agent.simulator.id_token import make_id_token
from tests.simulator.harness import AKI, BEN, GROUP_ID, scenario_of

pytestmark = pytest.mark.anyio
ORIGIN = "http://stand-in.test"


def make_clients() -> tuple[FakeLineServer, LineClient, LoginClient]:
    server = FakeLineServer(scenario_of().group)
    transport = httpx.ASGITransport(app=server.app)
    http = httpx.AsyncClient(transport=transport, base_url=ORIGIN)
    return server, LineClient("token", http_client=http), LoginClient(http_client=http)


async def test_a_reply_is_kept_and_its_token_works_once() -> None:
    server, line, _ = make_clients()
    server.issue_reply_token("rt1")
    assert await line.reply(
        "rt1", "hello", [Card("Kyoto", "temples", "https://example.com/k")]
    ) is (ReplyResult.SENT)
    assert await line.reply("rt1", "again") is ReplyResult.TOKEN_REFUSED
    [call] = server.sent_calls()
    assert call.kind == "reply" and call.target == "rt1"
    assert [message["type"] for message in call.messages] == ["text", "flex"]
    assert len(server.calls) == 2 and server.calls[1].status == 400


async def test_a_reply_with_a_token_nobody_issued_is_refused() -> None:
    server, line, _ = make_clients()
    assert await line.reply("made-up", "hello") is ReplyResult.TOKEN_REFUSED
    assert server.sent_calls() == []


async def test_a_push_keeps_its_messages_quick_replies_and_receiver() -> None:
    server, line, _ = make_clients()
    extra = OutgoingExtra({"type": "location", "title": "Cafe"}, "[位置] Cafe")
    await line.push(GROUP_ID, "hello", extras=[extra], quick_replies=[QuickReplyItem("Yes", "yes")])
    [call] = server.sent_calls()
    assert call.kind == "push" and call.target == GROUP_ID
    assert call.messages[-1]["quickReply"]["items"][0]["action"]["text"] == "yes"


async def test_more_messages_than_line_allows_are_refused_like_line_does() -> None:
    server, line, _ = make_clients()
    server.issue_reply_token("rt1")
    extras = [OutgoingExtra({"type": "text", "text": str(n)}, "x") for n in range(5)]
    assert await line.reply("rt1", "hello", extras=extras) is ReplyResult.MESSAGE_REFUSED
    with pytest.raises(LineApiError):
        await line.push(GROUP_ID, "hello", extras=extras)
    assert server.sent_calls() == []


async def test_the_names_and_the_members_are_the_scripted_groups() -> None:
    _, line, _ = make_clients()
    assert await line.get_member_name(GROUP_ID, AKI.user_id) == "Aki"
    assert await line.get_member_name(GROUP_ID, "Ustranger") is None
    assert await line.is_member(GROUP_ID, BEN.user_id) is True
    assert await line.is_member(GROUP_ID, "Ustranger") is False
    assert await line.is_member("Cother", BEN.user_id) is False
    assert await line.get_group_name(GROUP_ID) == "Trip friends"
    assert await line.get_group_name("Cother") is None


async def test_a_photo_a_member_sent_is_served_by_its_message_id() -> None:
    server, line, _ = make_clients()
    server.add_content("1001", b"bytes", "image/png")
    assert await line.get_message_content("1001") == (b"bytes", "image/png")
    assert await line.get_message_content("9999") is None


async def test_the_quota_is_unlimited_and_leaving_is_allowed() -> None:
    _, line, _ = make_clients()
    assert await line.get_remaining_messages() == 10**9
    await line.leave_group(GROUP_ID)


async def test_the_login_check_reads_the_member_out_of_a_token_it_knows() -> None:
    server, _, login = make_clients()
    claims = await login.verify_id_token(make_id_token(AKI.user_id, AKI.name), "12345")
    assert claims is not None
    assert (claims["sub"], claims["aud"], claims["name"]) == (AKI.user_id, "12345", "Aki")
    assert claims["iss"] == "https://access.line.me"
    assert await login.verify_id_token("forged", "12345") is None
    assert [call.path for call in server.calls].count("/oauth2/v2.1/verify") == 2


async def test_the_member_list_and_the_loading_mark_are_answered() -> None:
    server, _, _ = make_clients()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url=ORIGIN
    ) as http:
        ids = await http.get(f"/v2/bot/group/{GROUP_ID}/members/ids")
        assert ids.json() == {"memberIds": [AKI.user_id, BEN.user_id]}
        loading = await http.post("/v2/bot/chat/loading/start", json={"chatId": AKI.user_id})
        assert loading.status_code == 202
