"""Read the fields this agent needs from a LINE webhook event object.

Pure functions over the parsed JSON; called by the event dispatcher.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

MILLISECONDS_PER_SECOND = 1000


def group_id_of(event: dict[str, Any]) -> str | None:
    """Return the group the event happened in, or None for a non-group chat."""
    source = event.get("source") or {}
    if source.get("type") != "group":
        return None
    group_id = source.get("groupId")
    return group_id if isinstance(group_id, str) and group_id else None


def is_text_message(event: dict[str, Any]) -> bool:
    """Return whether the event is a text message."""
    message = event.get("message") or {}
    return (
        event.get("type") == "message"
        and message.get("type") == "text"
        and isinstance(message.get("text"), str)
    )


def is_self_mentioned(event: dict[str, Any]) -> bool:
    """Return whether the message mentions this bot (LINE marks it `isSelf: true`)."""
    message = event.get("message") or {}
    mention = message.get("mention") or {}
    mentionees = mention.get("mentionees") or []
    return any(isinstance(m, dict) and m.get("isSelf") is True for m in mentionees)


def local_time_of(event: dict[str, Any]) -> str:
    """Return the event's time as ISO 8601 in this machine's time zone."""
    timestamp = event.get("timestamp")
    if isinstance(timestamp, int) and not isinstance(timestamp, bool):
        moment = datetime.fromtimestamp(timestamp / MILLISECONDS_PER_SECOND).astimezone()
    else:
        moment = datetime.now().astimezone()
    return moment.isoformat(timespec="seconds")
