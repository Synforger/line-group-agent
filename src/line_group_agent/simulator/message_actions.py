"""List the actions (buttons) inside LINE messages the bot sent, in one fixed order.

A scenario's `press` and `open_liff` steps name an action by its place in this list, and the
chat page numbers its buttons the same way. Pure functions over the message objects.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

QUICK_REPLY_KEY = "quickReply"
BUBBLE_PARTS = ("header", "hero", "body", "footer")


def list_actions(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the action objects of the messages: for each message the actions found in its
    content in the order they are drawn (a Flex bubble's header, hero, body, then footer),
    then those of its quick reply buttons."""
    actions: list[dict[str, Any]] = []
    for message in messages:
        content = {key: value for key, value in message.items() if key != QUICK_REPLY_KEY}
        actions.extend(_actions_in(content))
        actions.extend(_actions_in(message.get(QUICK_REPLY_KEY)))
    return actions


def action_numbers(messages: Sequence[dict[str, Any]]) -> dict[int, int]:
    """Return the place of each action in `list_actions(messages)`, keyed by the action
    object's `id()`, so a renderer that holds the same objects can number its buttons."""
    return {id(action): number for number, action in enumerate(list_actions(messages))}


def _actions_in(node: Any) -> Iterator[dict[str, Any]]:
    if isinstance(node, dict):
        action = node.get("action")
        if isinstance(action, dict) and isinstance(action.get("type"), str):
            yield action
        for key in _drawing_order(node):
            if key != "action":
                yield from _actions_in(node[key])
    elif isinstance(node, list):
        for item in node:
            yield from _actions_in(item)


def _drawing_order(node: dict[str, Any]) -> list[str]:
    """Return the keys of a node in the order its content is drawn: a bubble's parts are
    drawn top to bottom whatever order the JSON lists them in."""
    if node.get("type") != "bubble":
        return list(node)
    return [part for part in BUBBLE_PARTS if part in node] + [
        key for key in node if key not in BUBBLE_PARTS
    ]
