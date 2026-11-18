"""Tell from the model's first answer of a turn that a long wait is ahead.

Pure; called by the answerer after the first request of a mention.
"""

from __future__ import annotations

from typing import Any

SERVER_TOOL_USE = "server_tool_use"
STILL_RUNNING_STOP_REASONS = ("pause_turn", "tool_use")


def is_slow_ahead(answer: dict[str, Any]) -> bool:
    """Return whether the answer stopped in the middle of web work that goes on: the
    turn was paused, or it stopped for a tool after the model ran a web tool."""
    stop_reason = answer.get("stop_reason")
    if stop_reason == "pause_turn":
        return True
    if stop_reason not in STILL_RUNNING_STOP_REASONS:
        return False
    content = answer.get("content") or []
    return any(isinstance(b, dict) and b.get("type") == SERVER_TOOL_USE for b in content)
