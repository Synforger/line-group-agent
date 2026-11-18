"""Take the thinking blocks out of earlier assistant messages before they are sent again.

A thinking block's signature is tied to the system text and the tool list of the request
that made it. When either changes (a new persona, a new version, a changed setting) the API
refuses every old block, so the group's conversation would stop. The blocks of earlier
turns are not needed to carry on, so they are left out of what is sent; the record keeps
them. Pure; called by the answerer for the history of a turn and by the rollover for the
conversation it summarizes.
"""

from __future__ import annotations

from typing import Any

THINKING_BLOCK_TYPES = ("thinking", "redacted_thinking")


def without_thinking(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a copy of `messages` whose assistant messages have no thinking blocks.

    An assistant message that held nothing else is left out. Messages are not changed in
    place, and a conversation without thinking comes back equal to what went in.
    """
    kept: list[dict[str, Any]] = []
    for message in messages:
        content = message.get("content")
        if message.get("role") != "assistant" or not isinstance(content, list):
            kept.append(message)
            continue
        blocks = [block for block in content if not _is_thinking(block)]
        if blocks:
            kept.append({**message, "content": blocks})
    return kept


def _is_thinking(block: Any) -> bool:
    return isinstance(block, dict) and block.get("type") in THINKING_BLOCK_TYPES
