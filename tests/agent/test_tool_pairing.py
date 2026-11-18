from typing import Any

from line_group_agent.agent.tool_pairing import UNANSWERED_TOOL_RESULT, pair_tool_calls


def call(number: int) -> dict[str, Any]:
    return {"type": "tool_use", "id": f"toolu_{number}", "name": "search_history", "input": {}}


def result(number: int) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": f"toolu_{number}", "content": "ok"}


def test_a_conversation_whose_calls_are_all_answered_is_unchanged() -> None:
    messages = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": [call(1)]},
        {"role": "user", "content": [result(1)]},
        {"role": "assistant", "content": [{"type": "text", "text": "a"}]},
    ]
    assert pair_tool_calls(messages) == messages


def test_a_missing_result_is_added_at_the_start_of_the_next_user_turn() -> None:
    messages = [
        {"role": "assistant", "content": [call(1), call(2)]},
        {"role": "user", "content": "next question"},
    ]
    paired = pair_tool_calls(messages)
    assert len(paired) == 2
    blocks = paired[1]["content"]
    assert [b["tool_use_id"] for b in blocks[:2]] == ["toolu_1", "toolu_2"]
    assert blocks[0]["is_error"] is True and blocks[0]["content"] == UNANSWERED_TOOL_RESULT
    assert blocks[2] == {"type": "text", "text": "next question"}


def test_only_the_missing_results_are_added() -> None:
    messages = [
        {"role": "assistant", "content": [call(1), call(2)]},
        {"role": "user", "content": [result(1)]},
    ]
    blocks = pair_tool_calls(messages)[1]["content"]
    assert [b["tool_use_id"] for b in blocks] == ["toolu_1", "toolu_2"]
    assert blocks[0]["content"] == "ok"


def test_a_call_at_the_end_gets_a_user_turn_of_results() -> None:
    paired = pair_tool_calls([{"role": "assistant", "content": [call(1)]}])
    assert paired[1]["role"] == "user" and paired[1]["content"][0]["tool_use_id"] == "toolu_1"


def test_a_call_followed_by_an_assistant_turn_gets_a_user_turn_between() -> None:
    messages = [
        {"role": "assistant", "content": [call(1)]},
        {"role": "assistant", "content": [{"type": "text", "text": "more"}]},
    ]
    assert [m["role"] for m in pair_tool_calls(messages)] == ["assistant", "user", "assistant"]


def test_the_input_is_not_changed_and_the_repair_is_the_same_every_time() -> None:
    messages = [
        {"role": "assistant", "content": [call(1)]},
        {"role": "user", "content": "q"},
    ]
    before = [dict(m) for m in messages]
    assert pair_tool_calls(messages) == pair_tool_calls(messages)
    assert messages == before
