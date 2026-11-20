import asyncio
import json
from pathlib import Path

import pytest

from line_group_agent.agent.answerer import DUPLICATE_CALL_RESULT
from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.client_tools import ClientTools
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import answer, text_answer
from tests.world import GROUP, build_world

pytestmark = pytest.mark.anyio
MENTION = GroupMessage("2026-11-18T12:00:00+09:00", "99", "U1", "Aki", "@bot go")


def noisy_tool(name: str = "noisy") -> ClientTool:
    def run(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        turn.output.add(OutgoingExtra({"type": "location"}, "[位置] here"))
        turn.output.quick_replies[:] = [QuickReplyItem("A", "A")]
        return ToolOutcome(f"ran with {json.dumps(tool_input)} for {turn.group_id}")

    return ClientTool(name, {"name": name, "description": "d", "input_schema": {}}, run)


def call(name: str, tool_input: dict[str, object]) -> dict[str, object]:
    block = {"type": "tool_use", "id": "toolu_1", "name": name, "input": tool_input}
    return answer([block], stop_reason="tool_use")


def test_definitions_come_back_in_the_order_the_tools_were_added() -> None:
    tools = ClientTools([noisy_tool("a"), noisy_tool("b")])
    assert [d["name"] for d in tools.definitions()] == ["a", "b"]
    assert tools.has("a") and not tools.has("c") and not tools.has(None)


def test_a_name_used_twice_is_refused() -> None:
    with pytest.raises(ValueError, match="two tools"):
        ClientTools([noisy_tool("a"), noisy_tool("a")])


def test_the_output_keeps_room_for_three_extras_and_one_location() -> None:
    output = TurnOutput()
    for _ in range(MAX_EXTRA_MESSAGES):
        assert output.has_room()
        output.add(OutgoingExtra({"type": "flex"}, "x"))
    assert not output.has_room() and not output.has_location()
    output.extras[0] = OutgoingExtra({"type": "location"}, "y")
    assert output.has_location()


async def test_the_tools_are_sent_with_the_request_and_their_output_is_in_the_answer(
    tmp_path: Path,
) -> None:
    world = build_world(
        tmp_path,
        [call("noisy", {"k": 1}), text_answer("<reply>done</reply>", message_id="msg_2")],
        tools=[noisy_tool()],
    )
    result = await world.answerer.answer(GROUP, MENTION)
    assert result.text == "done"
    assert [e.record_line for e in result.extras] == ["[位置] here"]
    assert result.quick_replies == [QuickReplyItem("A", "A")]
    names = [t["name"] for t in world.client.messages.requests[0]["tools"]]
    assert "noisy" in names
    [tool_result] = world.client.messages.requests[1]["messages"][-1]["content"]
    assert tool_result["content"] == f'ran with {{"k": 1}} for {GROUP}'


async def test_an_extra_message_alone_is_still_an_answer(tmp_path: Path) -> None:
    world = build_world(
        tmp_path,
        [call("noisy", {}), text_answer("no reply tags", message_id="msg_2")],
        tools=[noisy_tool()],
    )
    result = await world.answerer.answer(GROUP, MENTION)
    assert result.text is None and len(result.extras) == 1


async def test_a_tool_that_fails_gives_the_model_an_error_result_and_the_answer_goes_on(
    tmp_path: Path,
) -> None:
    def broken(_tool_input: object, _turn: ToolTurn) -> ToolOutcome:
        raise OSError("disk full")

    tool = ClientTool("broken", {"name": "broken", "description": "d", "input_schema": {}}, broken)
    world = build_world(
        tmp_path,
        [call("broken", {}), text_answer("<reply>Sorry.</reply>", message_id="msg_2")],
        tools=[tool],
    )
    result = await world.answerer.answer(GROUP, MENTION)
    assert result.text == "Sorry."
    [tool_result] = world.client.messages.requests[1]["messages"][-1]["content"]
    assert tool_result["is_error"] is True and "disk full" not in tool_result["content"]


async def test_a_tool_that_waits_is_awaited_and_the_loop_keeps_running_meanwhile(
    tmp_path: Path,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        started.set()
        await release.wait()
        return ToolOutcome("waited")

    tool = ClientTool("slow", {"name": "slow", "description": "d", "input_schema": {}}, slow)
    world = build_world(
        tmp_path,
        [call("slow", {}), text_answer("<reply>done</reply>", message_id="msg_2")],
        tools=[tool],
    )
    turn = asyncio.create_task(world.answerer.answer(GROUP, MENTION))
    await asyncio.wait_for(started.wait(), timeout=5)
    ticks = 0
    for _ in range(3):
        await asyncio.sleep(0)
        ticks += 1
    assert ticks == 3 and not turn.done()
    release.set()
    assert (await asyncio.wait_for(turn, timeout=5)).text == "done"
    [tool_result] = world.client.messages.requests[1]["messages"][-1]["content"]
    assert tool_result["content"] == "waited"


def counting_tool(name: str, runs: list[object]) -> ClientTool:
    def run(tool_input: object, _turn: ToolTurn) -> ToolOutcome:
        runs.append(tool_input)
        return ToolOutcome(f"run {len(runs)}")

    return ClientTool(name, {"name": name, "description": "d", "input_schema": {}}, run)


def calls_together(*blocks: tuple[str, str, dict[str, object]]) -> dict[str, object]:
    content = [
        {"type": "tool_use", "id": id_, "name": name, "input": data} for id_, name, data in blocks
    ]
    return answer(content, stop_reason="tool_use")


async def test_the_same_call_twice_in_one_answer_runs_once(tmp_path: Path) -> None:
    runs: list[object] = []
    world = build_world(
        tmp_path,
        [
            calls_together(
                ("toolu_1", "poll", {"question": "Where?", "options": ["A", "B"]}),
                ("toolu_2", "poll", {"options": ["A", "B"], "question": "Where?"}),
            ),
            text_answer("<reply>done</reply>", message_id="msg_2"),
        ],
        tools=[counting_tool("poll", runs)],
    )
    await world.answerer.answer(GROUP, MENTION)
    assert len(runs) == 1
    first, second = world.client.messages.requests[1]["messages"][-1]["content"]
    assert (first["tool_use_id"], first["content"]) == ("toolu_1", "run 1")
    assert (second["tool_use_id"], second["content"]) == ("toolu_2", DUPLICATE_CALL_RESULT)
    assert "is_error" not in second


async def test_calls_that_differ_in_the_input_or_the_tool_all_run(tmp_path: Path) -> None:
    runs: list[object] = []
    world = build_world(
        tmp_path,
        [
            calls_together(
                ("toolu_1", "poll", {"question": "Where?"}),
                ("toolu_2", "poll", {"question": "When?"}),
                ("toolu_3", "other", {"question": "Where?"}),
            ),
            text_answer("<reply>done</reply>", message_id="msg_2"),
        ],
        tools=[counting_tool("poll", runs), counting_tool("other", runs)],
    )
    await world.answerer.answer(GROUP, MENTION)
    assert len(runs) == 3


async def test_the_same_call_in_a_later_round_runs_again(tmp_path: Path) -> None:
    runs: list[object] = []
    world = build_world(
        tmp_path,
        [
            calls_together(("toolu_1", "poll", {"question": "Where?"})),
            calls_together(("toolu_2", "poll", {"question": "Where?"})),
            text_answer("<reply>done</reply>", message_id="msg_3"),
        ],
        tools=[counting_tool("poll", runs)],
    )
    await world.answerer.answer(GROUP, MENTION)
    assert len(runs) == 2
