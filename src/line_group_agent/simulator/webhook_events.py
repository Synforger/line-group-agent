"""Build the webhook events LINE would send for what a member does, and sign a request body.

Pure shape-building; called by the scenario runner. The shapes follow LINE's webhook event
objects for a group chat: a message (text, image, location) and a postback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventIds:
    """The identifiers one event carries; the runner makes a fresh set for each."""

    reply_token: str
    webhook_event_id: str
    message_id: str
    quote_token: str
    timestamp_ms: int


@dataclass(frozen=True)
class BotMention:
    """The bot being @-mentioned: the text starts with `@<name>`."""

    user_id: str
    name: str


def text_event(
    group_id: str, user_id: str, text: str, ids: EventIds, mention: BotMention | None = None
) -> dict[str, Any]:
    """Return the event of a text message; with `mention` the text is prefixed by the
    @-mention of the bot and the message says so the way LINE does."""
    message: dict[str, Any] = {"id": ids.message_id, "type": "text", "quoteToken": ids.quote_token}
    if mention is None:
        message["text"] = text
    else:
        handle = f"@{mention.name}"
        message["text"] = f"{handle} {text}"
        message["mention"] = {
            "mentionees": [
                {
                    "index": 0,
                    "length": len(handle),
                    "userId": mention.user_id,
                    "type": "user",
                    "isSelf": True,
                }
            ]
        }
    return _message_event(group_id, user_id, ids, message)


def image_event(group_id: str, user_id: str, ids: EventIds) -> dict[str, Any]:
    """Return the event of a photo kept in LINE's own storage (the bot reads it by id)."""
    message = {
        "id": ids.message_id,
        "type": "image",
        "quoteToken": ids.quote_token,
        "contentProvider": {"type": "line"},
    }
    return _message_event(group_id, user_id, ids, message)


def location_event(
    group_id: str,
    user_id: str,
    ids: EventIds,
    *,
    title: str,
    address: str,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    """Return the event of a shared pin."""
    message = {
        "id": ids.message_id,
        "type": "location",
        "title": title,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
    }
    return _message_event(group_id, user_id, ids, message)


def postback_event(group_id: str, user_id: str, data: str, ids: EventIds) -> dict[str, Any]:
    """Return the event of a button that sends a postback."""
    return {
        "type": "postback",
        "mode": "active",
        "timestamp": ids.timestamp_ms,
        "source": _source(group_id, user_id),
        "webhookEventId": ids.webhook_event_id,
        "deliveryContext": {"isRedelivery": False},
        "replyToken": ids.reply_token,
        "postback": {"data": data},
    }


def webhook_body(events: list[dict[str, Any]], destination: str) -> bytes:
    """Return the request body LINE posts: the bot's user id and the events."""
    payload = {"destination": destination, "events": events}
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def sign_body(body: bytes, channel_secret: str) -> str:
    """Return the `X-Line-Signature` value: the base64 HMAC-SHA256 of the raw body."""
    digest = hmac.new(channel_secret.encode("utf-8"), body, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def _message_event(
    group_id: str, user_id: str, ids: EventIds, message: dict[str, Any]
) -> dict[str, Any]:
    return {
        "type": "message",
        "mode": "active",
        "timestamp": ids.timestamp_ms,
        "source": _source(group_id, user_id),
        "webhookEventId": ids.webhook_event_id,
        "deliveryContext": {"isRedelivery": False},
        "replyToken": ids.reply_token,
        "message": message,
    }


def _source(group_id: str, user_id: str) -> dict[str, str]:
    return {"type": "group", "groupId": group_id, "userId": user_id}
