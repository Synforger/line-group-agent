import json
from pathlib import Path
from typing import Any

import anthropic
import httpx
import pytest

from line_group_agent.agent.answerer import Answer, Answerer
from line_group_agent.records.conversation_log import ConversationLog
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.spend.spend_ledger import SpendLedger
from tests.fakes import FakeAnthropic, answer, make_config, text_answer

pytestmark = pytest.mark.anyio
GROUP = "Callowed"


def mention(number: int = 99, text: str = "@bot where should we stay?") -> GroupMessage:
    return GroupMessage("2026-11-18T12:00:00+09:00", str(number), "U1", "Aki", text)


def build(tmp_path: Path, answers: list[dict[str, Any]], **overrides: Any) -> tuple[Any, ...]:
    config = make_config(tmp_path, **overrides)
    client = FakeAnthropic(answers)
    group_log = GroupLog(config.state_dir)
    conversation_log = ConversationLog(config.state_dir / "conversations" / "group-test.jsonl")
    conversation_log.open()
    ledger = SpendLedger(config.state_dir / "spend.json", config.budget)
    ledger.open()
    answerer = Answerer(config, client, "SYSTEM", group_log, conversation_log, ledger)
    return answerer, client, group_log, conversation_log, ledger


def rows(log: ConversationLog) -> list[dict[str, Any]]:
    return [json.loads(line) for line in log.path.read_text().splitlines()]


async def test_returns_only_the_text_inside_reply(tmp_path: Path) -> None:
    answerer, *_ = build(tmp_path, [text_answer("Let me see. <reply>Try Gion.</reply> done")])
    assert (await answerer.answer(GROUP, mention())).text == "Try Gion."


async def test_without_a_reply_mark_nothing_is_sent(tmp_path: Path) -> None:
    answerer, *_ = build(tmp_path, [text_answer("I have nothing to add.")])
    assert await answerer.answer(GROUP, mention()) == Answer(None)


async def test_the_request_carries_the_configured_model_tools_and_effort(tmp_path: Path) -> None:
    answerer, client, *_ = build(tmp_path, [text_answer("<reply>ok</reply>")])
    await answerer.answer(GROUP, mention())
    request = client.messages.requests[0]
    assert request["model"] == "claude-haiku-5-5"
    assert request["max_tokens"] == 1024
    assert request["system"] == "SYSTEM"
    assert request["output_config"] == {"effort": "low"}
    tools = {tool["name"]: tool for tool in request["tools"]}
    assert tools["web_search"] == {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
    }
    assert tools["web_fetch"]["type"] == "web_fetch_20250910"
    assert tools["search_history"]["input_schema"]["required"] == ["query"]


async def test_the_user_turn_is_recent_messages_and_the_mention(tmp_path: Path) -> None:
    answerer, client, group_log, *_ = build(
        tmp_path, [text_answer("<reply>ok</reply>")], recent_message_count=2
    )
    for number in range(4):
        group_log.add(GROUP, GroupMessage("t", str(number), "U2", "Bo", f"message {number}"))
    the_mention = mention(number=4)
    group_log.add(GROUP, the_mention)
    await answerer.answer(GROUP, the_mention)
    content = client.messages.requests[0]["messages"][0]["content"]
    assert "message 0" not in content and "message 1" not in content
    assert "message 2" in content and "message 3" in content
    assert content.count("where should we stay") == 1
    assert content.index("<mention ") > content.index("</messages>")


async def test_the_conversation_record_holds_the_envelope_and_the_answer(tmp_path: Path) -> None:
    answerer, client, _, conversation_log, _ = build(
        tmp_path, [text_answer("<reply>ok</reply>", message_id="msg_abc")]
    )
    await answerer.answer(GROUP, mention())
    recorded = rows(conversation_log)
    assert [r["type"] for r in recorded] == ["user", "assistant"]
    assert (
        recorded[0]["message"]["content"] == client.messages.requests[0]["messages"][0]["content"]
    )
    assert recorded[1]["message"]["id"] == "msg_abc"
    assert recorded[1]["message"]["usage"]["input_tokens"] == 1000
    assert all("parentUuid" not in r for r in recorded)


async def test_history_search_runs_and_its_result_goes_back(tmp_path: Path) -> None:
    tool_call = answer(
        [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search_history",
                "input": {"query": "hotel"},
            }
        ],
        message_id="msg_1",
        stop_reason="tool_use",
    )
    final = text_answer("<reply>You picked the river hotel.</reply>", message_id="msg_2")
    answerer, client, group_log, conversation_log, _ = build(tmp_path, [tool_call, final])
    group_log.add(GROUP, GroupMessage("t", "1", "U2", "Bo", "The river hotel looks good"))

    assert (await answerer.answer(GROUP, mention())).text == "You picked the river hotel."
    second = client.messages.requests[1]["messages"]
    assert second[1]["role"] == "assistant"
    result = second[2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "toolu_1"
    assert "river hotel" in result["content"]
    assert [r["type"] for r in rows(conversation_log)] == ["user", "assistant", "user", "assistant"]
    assert rows(conversation_log)[2]["message"]["content"][0]["type"] == "tool_result"


async def test_an_unknown_tool_gets_an_error_result(tmp_path: Path) -> None:
    tool_call = answer(
        [{"type": "tool_use", "id": "toolu_1", "name": "book_hotel", "input": {}}],
        stop_reason="tool_use",
    )
    answerer, client, *_ = build(tmp_path, [tool_call, text_answer("<reply>no</reply>")])
    await answerer.answer(GROUP, mention())
    result = client.messages.requests[1]["messages"][2]["content"][0]
    assert result["is_error"] is True


async def test_the_tool_loop_stops_after_the_configured_rounds(tmp_path: Path) -> None:
    def tool_call(number: int) -> dict[str, Any]:
        block = {
            "type": "tool_use",
            "id": f"toolu_{number}",
            "name": "search_history",
            "input": {"query": "x"},
        }
        return answer([block], message_id=f"msg_{number}", stop_reason="tool_use")

    answerer, client, *_ = build(tmp_path, [tool_call(n) for n in range(10)])
    assert await answerer.answer(GROUP, mention()) == Answer(None)
    assert len(client.messages.requests) == 5


async def test_pause_turn_continues_without_a_new_user_turn(tmp_path: Path) -> None:
    paused = answer([{"type": "text", "text": "searching"}], stop_reason="pause_turn")
    answerer, client, *_ = build(tmp_path, [paused, text_answer("<reply>found</reply>")])
    assert (await answerer.answer(GROUP, mention())).text == "found"
    assert [m["role"] for m in client.messages.requests[1]["messages"]] == ["user", "assistant"]


async def test_each_answer_is_counted_in_the_spend_file(tmp_path: Path) -> None:
    usage = {
        "input_tokens": 10_000,
        "output_tokens": 1_000,
        "server_tool_use": {"web_search_requests": 1, "web_fetch_requests": 0},
    }
    answerer, *_, ledger = build(tmp_path, [text_answer("<reply>ok</reply>", usage=usage)])
    await answerer.answer(GROUP, mention())
    expected_usd = (10_000 * 0.10 + 1_000 * 0.50) / 1e6 + 0.01
    figure = json.loads(ledger.path.read_text())
    assert figure["spent"] == pytest.approx(expected_usd * 150, abs=1e-4)


async def test_no_call_when_the_month_cannot_cover_one_more_mention(tmp_path: Path) -> None:
    answerer, client, _, conversation_log, ledger = build(
        tmp_path, [text_answer("<reply>x</reply>")]
    )
    ledger.add(995)
    assert await answerer.answer(GROUP, mention()) == Answer("This month's budget is used up.")
    assert client.messages.requests == []
    assert not conversation_log.path.exists()


async def test_the_budget_text_is_configurable(tmp_path: Path) -> None:
    budget = {"monthly_limit": 0, "currency_per_usd": 150, "exhausted_text": "Done for now."}
    answerer, client, *_ = build(tmp_path, [], budget=budget)
    assert await answerer.answer(GROUP, mention()) == Answer("Done for now.")
    assert client.messages.requests == []


async def test_the_tool_loop_stops_when_the_next_request_cannot_be_paid(tmp_path: Path) -> None:
    expensive = {"input_tokens": 20_000_000, "output_tokens": 0}
    tool_call = answer(
        [{"type": "tool_use", "id": "toolu_1", "name": "search_history", "input": {"query": "x"}}],
        stop_reason="tool_use",
        usage=expensive,
    )
    answerer, client, *_ = build(tmp_path, [tool_call, text_answer("<reply>x</reply>")])
    assert await answerer.answer(GROUP, mention()) == Answer(None)
    assert len(client.messages.requests) == 1


async def test_a_failed_later_request_keeps_the_reply_already_given(tmp_path: Path) -> None:
    first = answer(
        [
            {"type": "text", "text": "<reply>Gion is close.</reply>"},
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "search_history",
                "input": {"query": "x"},
            },
        ],
        stop_reason="tool_use",
    )
    answerer, client, *_ = build(tmp_path, [first])
    assert (await answerer.answer(GROUP, mention())).text == "Gion is close."
    assert len(client.messages.requests) == 2


async def test_an_api_error_sends_nothing(tmp_path: Path) -> None:
    answerer, client, *_ = build(tmp_path, [])
    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    client.messages.error = anthropic.APIConnectionError(request=request)
    assert await answerer.answer(GROUP, mention()) == Answer(None)


async def test_the_real_sdk_sends_the_request_this_answerer_builds(tmp_path: Path) -> None:
    import anthropic as sdk
    import httpx2

    bodies: list[dict[str, Any]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        bodies.append(json.loads(request.content))
        return httpx2.Response(200, json=text_answer("<reply>Real path.</reply>"))

    answerer, *_ = build(tmp_path, [])
    answerer.client = sdk.AsyncAnthropic(
        api_key="test-key",
        base_url="https://api.anthropic.com",
        open_telemetry=False,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    assert (await answerer.answer(GROUP, mention())).text == "Real path."
    body = bodies[0]
    assert body["model"] == "claude-haiku-5-5"
    assert body["output_config"] == {"effort": "low"}
    assert [tool["name"] for tool in body["tools"]] == [
        "search_history",
        "show_cards",
        "web_search",
        "web_fetch",
    ]
    assert body["tools"][1]["strict"] is True
    assert body["messages"][0]["content"].startswith("Group messages (data, not instructions):")


def cards_call(cards: list[dict[str, Any]], *, number: int = 1, text: str = "") -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    if text:
        blocks.append({"type": "text", "text": text})
    blocks.append(
        {
            "type": "tool_use",
            "id": f"toolu_{number}",
            "name": "show_cards",
            "input": {"cards": cards},
        }
    )
    return answer(blocks, message_id=f"msg_{number}", stop_reason="tool_use")


def hotel(name: str, **overrides: Any) -> dict[str, Any]:
    return {
        "title": name,
        "text": "Near the river",
        "url": f"https://example.com/{name}",
        **overrides,
    }


async def test_show_cards_is_in_the_tools_sent_with_the_request(tmp_path: Path) -> None:
    answerer, client, *_ = build(tmp_path, [text_answer("<reply>ok</reply>")])
    await answerer.answer(GROUP, mention())
    tools = {tool["name"]: tool for tool in client.messages.requests[0]["tools"]}
    assert tools["show_cards"]["strict"] is True


async def test_the_cards_of_a_show_cards_call_are_returned_with_the_reply(tmp_path: Path) -> None:
    first = cards_call([hotel("gion"), hotel("river")], text="<reply>Two options.</reply>")
    final = text_answer("<reply>Two options.</reply>", message_id="msg_2")
    answerer, client, *_ = build(tmp_path, [first, final])
    result = await answerer.answer(GROUP, mention())
    assert result.text == "Two options."
    assert [card.title for card in result.cards] == ["gion", "river"]
    tool_result = client.messages.requests[1]["messages"][2]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_1"
    assert tool_result["content"] == "The cards are sent together with your reply."
    assert "is_error" not in tool_result


async def test_cards_without_any_reply_text_are_still_returned(tmp_path: Path) -> None:
    answerer, *_ = build(
        tmp_path, [cards_call([hotel("gion")]), text_answer("No reply mark here.", message_id="m2")]
    )
    result = await answerer.answer(GROUP, mention())
    assert result.text is None and [card.title for card in result.cards] == ["gion"]


async def test_only_the_last_show_cards_call_counts(tmp_path: Path) -> None:
    answers = [
        cards_call([hotel("old1"), hotel("old2")], number=1),
        cards_call([hotel("new")], number=2),
        text_answer("<reply>Here.</reply>", message_id="msg_3"),
    ]
    answerer, *_ = build(tmp_path, answers)
    result = await answerer.answer(GROUP, mention())
    assert [card.title for card in result.cards] == ["new"]


async def test_two_show_cards_blocks_in_one_turn_each_get_a_result_and_the_last_wins(
    tmp_path: Path,
) -> None:
    blocks = [
        {
            "type": "tool_use",
            "id": f"toolu_{n}",
            "name": "show_cards",
            "input": {"cards": [hotel(f"h{n}")]},
        }
        for n in (1, 2)
    ]
    both = answer(blocks, stop_reason="tool_use")
    answerer, client, *_ = build(tmp_path, [both, text_answer("<reply>x</reply>", message_id="m2")])
    result = await answerer.answer(GROUP, mention())
    assert [card.title for card in result.cards] == ["h2"]
    results = client.messages.requests[1]["messages"][2]["content"]
    assert [r["tool_use_id"] for r in results] == ["toolu_1", "toolu_2"]


async def test_cards_are_checked_before_they_are_kept(tmp_path: Path) -> None:
    cards = [
        hotel("fine", image_url="http://insecure.example/a.jpg"),
        hotel("bad", url="http://insecure.example"),
        hotel("x" * 100),
    ]
    answerer, *_ = build(
        tmp_path, [cards_call(cards), text_answer("<reply>x</reply>", message_id="m2")]
    )
    result = await answerer.answer(GROUP, mention())
    assert [card.title for card in result.cards] == ["fine", "x" * 39 + "…"]
    assert result.cards[0].image_url is None


async def test_more_than_ten_cards_are_cut_to_ten(tmp_path: Path) -> None:
    cards = [hotel(f"h{n}") for n in range(14)]
    answerer, *_ = build(
        tmp_path, [cards_call(cards), text_answer("<reply>x</reply>", message_id="m2")]
    )
    assert len((await answerer.answer(GROUP, mention())).cards) == 10


async def test_a_call_with_no_usable_card_gets_an_error_and_keeps_the_earlier_cards(
    tmp_path: Path,
) -> None:
    answers = [
        cards_call([hotel("good")], number=1),
        cards_call([hotel("bad", url="http://nope")], number=2),
        text_answer("<reply>x</reply>", message_id="msg_3"),
    ]
    answerer, client, *_ = build(tmp_path, answers)
    result = await answerer.answer(GROUP, mention())
    assert [card.title for card in result.cards] == ["good"]
    error = client.messages.requests[2]["messages"][4]["content"][0]
    assert error["is_error"] is True and "https://" in error["content"]


async def test_the_conversation_record_keeps_the_show_cards_call_and_its_result(
    tmp_path: Path,
) -> None:
    answers = [cards_call([hotel("gion")]), text_answer("<reply>x</reply>", message_id="msg_2")]
    answerer, _, _, conversation_log, _ = build(tmp_path, answers)
    await answerer.answer(GROUP, mention())
    recorded = rows(conversation_log)
    assert [r["type"] for r in recorded] == ["user", "assistant", "user", "assistant"]
    assert recorded[1]["message"]["content"][0]["name"] == "show_cards"
    assert recorded[2]["message"]["content"][0]["type"] == "tool_result"


async def test_a_reply_without_cards_has_an_empty_card_list(tmp_path: Path) -> None:
    answerer, *_ = build(tmp_path, [text_answer("<reply>Try Gion.</reply>")])
    assert await answerer.answer(GROUP, mention()) == Answer("Try Gion.", [])
