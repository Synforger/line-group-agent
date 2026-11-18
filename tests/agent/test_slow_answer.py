from line_group_agent.agent.slow_answer import is_slow_ahead
from tests.fakes import answer, text_answer

WEB_SEARCH = {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {}}
CLIENT_TOOL = {"type": "tool_use", "id": "toolu_1", "name": "search_history", "input": {}}


def test_a_paused_turn_is_slow() -> None:
    assert is_slow_ahead(text_answer("searching", stop_reason="pause_turn"))


def test_a_stop_for_a_tool_after_a_web_search_is_slow() -> None:
    assert is_slow_ahead(answer([WEB_SEARCH, CLIENT_TOOL], stop_reason="tool_use"))


def test_a_stop_for_a_client_tool_alone_is_not_slow() -> None:
    assert not is_slow_ahead(answer([CLIENT_TOOL], stop_reason="tool_use"))


def test_a_finished_answer_is_not_slow_even_after_a_web_search() -> None:
    assert not is_slow_ahead(answer([WEB_SEARCH, {"type": "text", "text": "x"}]))
