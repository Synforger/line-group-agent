"""Read the fields this agent needs from a LINE webhook event object.

Pure functions over the parsed JSON; called by the event dispatcher.
"""

from __future__ import annotations

import re
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


TEXT_KIND = "text"
IMAGE_KIND = "image"
LOCATION_KIND = "location"


def message_kind_of(event: dict[str, Any]) -> str | None:
    """Return `text`, `image` or `location` for a message event the agent records, None for
    any other event or kind of message (a sticker, a video, a file …)."""
    if is_text_message(event):
        return TEXT_KIND
    message = event.get("message") or {}
    if event.get("type") == "message" and message.get("type") in (IMAGE_KIND, LOCATION_KIND):
        return str(message["type"])
    return None


def is_external_image(event: dict[str, Any]) -> bool:
    """Return whether the image sits at an address of the sender's (LINE cannot give its
    content), not in LINE's own storage."""
    provider = (event.get("message") or {}).get("contentProvider") or {}
    return provider.get("type") == "external"


def quote_token_of(event: dict[str, Any]) -> str | None:
    """Return the token that quotes the event's message in a reply, or None without one."""
    token = (event.get("message") or {}).get("quoteToken")
    return token if isinstance(token, str) and token else None


def unsent_message_id_of(event: dict[str, Any]) -> str | None:
    """Return the id of the message an unsend event took back, or None for any other event."""
    if event.get("type") != "unsend":
        return None
    message_id = (event.get("unsend") or {}).get("messageId")
    return message_id if isinstance(message_id, str) and message_id else None


def postback_of(event: dict[str, Any]) -> tuple[str, str | None] | None:
    """Return the data of a postback event and the id of the member who pressed the button
    (None when LINE gives none), or None for any other event."""
    if event.get("type") != "postback":
        return None
    data = (event.get("postback") or {}).get("data")
    if not isinstance(data, str) or not data:
        return None
    user_id = (event.get("source") or {}).get("userId")
    return data, user_id if isinstance(user_id, str) and user_id else None


def webhook_event_id_of(event: dict[str, Any]) -> str | None:
    """Return the id LINE gives an event (the same one when it sends the event again)."""
    event_id = event.get("webhookEventId")
    return event_id if isinstance(event_id, str) and event_id else None


def is_self_mentioned(event: dict[str, Any]) -> bool:
    """Return whether the message mentions this bot (LINE marks it `isSelf: true`)."""
    message = event.get("message") or {}
    mention = message.get("mention") or {}
    mentionees = mention.get("mentionees") or []
    return any(isinstance(m, dict) and m.get("isSelf") is True for m in mentionees)


# What may sit around a name used to call the bot: spaces, and the punctuation people
# put after a name ("ソラ、" "sora," "SORA!").
_EDGE = " \t\u3000、。,.!！?？~〜ー…"


def is_called_by_name(
    event: dict[str, Any], names: tuple[str, ...], *, start_runs_on: bool = False
) -> bool:
    """Return whether a text message starts or ends with one of `names` (any case).

    A name only counts at the start or the end, so a message that merely talks about
    the bot in the middle of a sentence is not taken as a call. At the start the name
    must be followed by a space or punctuation ("ソラ、" calls, "ソラって便利" does
    not), unless `start_runs_on` is set: then any text may follow it ("ソラ候補出して"
    calls, as people writing without spaces do), except that a Latin name must not run
    on into more letters or digits. At the end a Latin name must not be the tail of a
    longer word.
    """
    message = event.get("message") or {}
    text = message.get("text")
    if not isinstance(text, str) or not names:
        return False
    body = text.strip(_EDGE).casefold()
    for name in names:
        key = name.casefold()
        after = body[len(key) : len(key) + 1]
        if body.startswith(key) and (not after or after in _EDGE):
            return True
        if start_runs_on and body.startswith(key) and not (_runs_on(key[-1]) and _runs_on(after)):
            return True
        if body.endswith(key) and not _runs_on(body[-len(key) - 1 : -len(key)]):
            return True
    return False


def is_name_in_text(event: dict[str, Any], names: tuple[str, ...]) -> bool:
    """Return whether a text message holds one of `names` anywhere (any case).

    A Latin name does not count when it is part of a longer word ("Sora" in "Soraya"
    or "mysora"); a name written in other scripts counts wherever it stands. Used for a
    message that may only talk about the bot, so the model decides whether to answer.
    """
    text = (event.get("message") or {}).get("text")
    if not isinstance(text, str):
        return False
    body = text.casefold()
    return any(_holds_name(body, name.casefold()) for name in names if name)


def strip_call_name(text: str, names: tuple[str, ...]) -> str:
    """Return `text` without a call name at its start or its end (any case), with the
    spaces and punctuation next to it. Text that holds no call name is returned as is."""
    body = text.strip(_EDGE)
    for name in names:
        if body.casefold().startswith(name.casefold()):
            return body[len(name) :].strip(_EDGE)
        if body.casefold().endswith(name.casefold()):
            return body[: -len(name)].strip(_EDGE)
    return text


def _runs_on(neighbour: str) -> bool:
    return bool(neighbour) and bool(re.match(r"[a-z0-9]", neighbour))


def _holds_name(body: str, key: str) -> bool:
    """Whether `key` stands in `body` at least once without running on into a Latin word."""
    start = body.find(key)
    while start != -1:
        end = start + len(key)
        before = body[start - 1] if start > 0 else ""
        after = body[end : end + 1]
        is_run_on = (_runs_on(key[0]) and _runs_on(before)) or (
            _runs_on(key[-1]) and _runs_on(after)
        )
        if not is_run_on:
            return True
        start = body.find(key, start + 1)
    return False


def is_redelivery(event: dict[str, Any]) -> bool:
    """Return whether LINE sent this event again after an earlier delivery failed."""
    context = event.get("deliveryContext") or {}
    return context.get("isRedelivery") is True


def age_seconds_of(event: dict[str, Any], now: datetime) -> float | None:
    """Return how many seconds ago the event happened, or None without a timestamp."""
    timestamp = event.get("timestamp")
    if not isinstance(timestamp, int) or isinstance(timestamp, bool):
        return None
    return now.timestamp() - timestamp / MILLISECONDS_PER_SECOND


def local_time_of(event: dict[str, Any]) -> str:
    """Return the event's time as ISO 8601 in this machine's time zone."""
    timestamp = event.get("timestamp")
    if isinstance(timestamp, int) and not isinstance(timestamp, bool):
        moment = datetime.fromtimestamp(timestamp / MILLISECONDS_PER_SECOND).astimezone()
    else:
        moment = datetime.now().astimezone()
    return moment.isoformat(timespec="seconds")
