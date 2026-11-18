"""Make sure every tool call in a conversation has its result, before it is sent.

A turn can end with a tool call whose result was never recorded (the round limit was
reached, or the agent stopped in between). The API refuses such a conversation, so the
missing results are filled in with an error result, the same way every time so the
cached prefix does not change. Pure; called by the answerer and the rollover.
"""

from __future__ import annotations

from typing import Any

UNANSWERED_TOOL_RESULT = "This tool call was not run."


def pair_tool_calls(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of `messages` in which each assistant tool call is answered by a
    tool result at the start of the next user turn (added when it is missing)."""
    paired: list[dict[str, Any]] = []
    for message in messages:
        if paired and _needs_results(paired[-1]):
            if message["role"] == "user":
                message = _with_results(message, _missing_results(paired[-1], message))
            else:
                paired.append({"role": "user", "content": _missing_results(paired[-1], None)})
        paired.append(message)
    if paired and _needs_results(paired[-1]):
        paired.append({"role": "user", "content": _missing_results(paired[-1], None)})
    return paired


def _needs_results(message: dict[str, Any]) -> bool:
    return message["role"] == "assistant" and bool(_call_ids(message))


def _call_ids(message: dict[str, Any]) -> list[str]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [b["id"] for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]


def _missing_results(
    assistant: dict[str, Any], user: dict[str, Any] | None
) -> list[dict[str, Any]]:
    answered: set[str] = set()
    if user is not None and isinstance(user.get("content"), list):
        answered = {
            b.get("tool_use_id")
            for b in user["content"]
            if isinstance(b, dict) and b.get("type") == "tool_result"
        }
    return [
        {
            "type": "tool_result",
            "tool_use_id": call_id,
            "content": UNANSWERED_TOOL_RESULT,
            "is_error": True,
        }
        for call_id in _call_ids(assistant)
        if call_id not in answered
    ]


def _with_results(user: dict[str, Any], missing: list[dict[str, Any]]) -> dict[str, Any]:
    if not missing:
        return user
    content = user["content"]
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
    existing = [b for b in blocks if b.get("type") == "tool_result"]
    others = [b for b in blocks if b.get("type") != "tool_result"]
    return {"role": "user", "content": [*existing, *missing, *others]}
