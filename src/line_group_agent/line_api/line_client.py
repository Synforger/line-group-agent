"""The calls this agent makes to the LINE Messaging API: reply, push, member name,
group name, membership check, leaving a group and the message quota.

A reply or push carries the answer's text (which can quote a message), after it one Flex
Message holding the cards, then the extra messages the tools made (a poll card, a
location), and quick reply buttons on the last of them (LINE takes up to 5 messages per
call). The content of an image a member sent is read too. Called by the answer sender and
the media recorder. Errors carry the HTTP status only, never a token or what was sent.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

import httpx

from line_group_agent.cards.card import Card
from line_group_agent.line_api.flex_cards import build_flex_message
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem, build_quick_reply

API_BASE_URL = "https://api.line.me"
DATA_API_BASE_URL = "https://api-data.line.me"
MAX_CONTENT_BYTES = 20 * 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 15.0
TEXT_LIMIT_UTF16_UNITS = 5000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
TOKEN_REFUSED_MARKER = "reply token"
LIMITED_QUOTA = "limited"
UNLIMITED_MESSAGES = 10**9


class LineApiError(RuntimeError):
    """A LINE API call failed; `status` is the HTTP status (0 when no answer came)."""

    def __init__(self, action: str, status: int) -> None:
        super().__init__(f"LINE {action} failed with status {status}")
        self.status = status


class ReplyResult(StrEnum):
    """How LINE answered a reply."""

    SENT = "sent"
    TOKEN_REFUSED = "token_refused"
    MESSAGE_REFUSED = "message_refused"


class LineClient:
    """Sends text and cards to a group and looks up a member's display name."""

    def __init__(
        self,
        channel_access_token: str,
        *,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        # trust_env=False: no proxy or certificate settings from environment variables.
        self._http = http_client or httpx.AsyncClient(
            base_url=API_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False
        )
        self._headers = {"Authorization": f"Bearer {channel_access_token}"}

    async def reply(
        self,
        reply_token: str,
        text: str | None,
        cards: Sequence[Card] = (),
        *,
        with_images: bool = True,
        quote_token: str | None = None,
        extras: Sequence[OutgoingExtra] = (),
        quick_replies: Sequence[QuickReplyItem] = (),
    ) -> ReplyResult:
        """Answer an event with its reply token: the text first (quoting the message
        `quote_token` belongs to, when given), then the cards, then the extra messages,
        with the quick replies on the last message.

        `TOKEN_REFUSED` means the token was used or too old, so the caller can push.
        `MESSAGE_REFUSED` means LINE took the token but not the message, which only
        happens when more than text was sent: the caller may try the cards without images.
        A 400 on a text-only reply is always reported as a refused token.
        """
        messages = _messages(text, cards, with_images, quote_token, extras, quick_replies)
        body = {"replyToken": reply_token, "messages": messages}
        response = await self._post("/v2/bot/message/reply", body, "reply")
        if response.status_code == HTTP_OK:
            return ReplyResult.SENT
        if response.status_code == HTTP_BAD_REQUEST:
            if (cards or extras or quick_replies) and not _is_token_refusal(response):
                return ReplyResult.MESSAGE_REFUSED
            return ReplyResult.TOKEN_REFUSED
        raise LineApiError("reply", response.status_code)

    async def push(
        self,
        to: str,
        text: str | None,
        cards: Sequence[Card] = (),
        *,
        with_images: bool = True,
        quote_token: str | None = None,
        extras: Sequence[OutgoingExtra] = (),
        quick_replies: Sequence[QuickReplyItem] = (),
    ) -> None:
        """Send the text (quoting a message when `quote_token` is given), then the cards and
        the extra messages, to a group or a user (counts against the account's monthly
        message quota)."""
        messages = _messages(text, cards, with_images, quote_token, extras, quick_replies)
        body = {"to": to, "messages": messages}
        headers = {"X-Line-Retry-Key": str(uuid.uuid4())}
        response = await self._post("/v2/bot/message/push", body, "push", headers)
        if response.status_code != HTTP_OK:
            raise LineApiError("push", response.status_code)

    async def get_member_name(self, group_id: str, user_id: str) -> str | None:
        """Return a group member's display name, or None when LINE does not give it."""
        try:
            response = await self._http.get(
                f"/v2/bot/group/{group_id}/member/{user_id}", headers=self._headers
            )
        except httpx.HTTPError:
            return None
        if response.status_code != HTTP_OK:
            return None
        name = response.json().get("displayName")
        return name if isinstance(name, str) else None

    async def get_group_name(self, group_id: str) -> str | None:
        """Return the group's name, or None when LINE does not give it."""
        try:
            response = await self._http.get(
                f"/v2/bot/group/{group_id}/summary", headers=self._headers
            )
        except httpx.HTTPError:
            return None
        if response.status_code != HTTP_OK:
            return None
        name = response.json().get("groupName")
        return name if isinstance(name, str) and name else None

    async def get_message_content(self, message_id: str) -> tuple[bytes, str] | None:
        """Return the bytes and the content type of an image a member sent, or None when
        LINE does not give it (gone, an error, or larger than `MAX_CONTENT_BYTES`)."""
        url = f"{DATA_API_BASE_URL}/v2/bot/message/{message_id}/content"
        try:
            async with self._http.stream("GET", url, headers=self._headers) as response:
                if response.status_code != HTTP_OK:
                    return None
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > MAX_CONTENT_BYTES:
                        return None
                    chunks.append(chunk)
                content_type = response.headers.get("content-type", "")
        except httpx.HTTPError:
            return None
        return b"".join(chunks), content_type.split(";")[0].strip().lower()

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        """Return whether the user is in the group: True, False, or None when LINE
        gave no clear answer (an error or no connection)."""
        try:
            response = await self._http.get(
                f"/v2/bot/group/{group_id}/member/{user_id}", headers=self._headers
            )
        except httpx.HTTPError:
            return None
        if response.status_code == HTTP_OK:
            return True
        if response.status_code == HTTP_NOT_FOUND:
            return False
        return None

    async def leave_group(self, group_id: str) -> None:
        """Make the bot leave the group."""
        response = await self._post(f"/v2/bot/group/{group_id}/leave", {}, "leave")
        if response.status_code != HTTP_OK:
            raise LineApiError("leave", response.status_code)

    async def get_remaining_messages(self) -> int | None:
        """Return how many more messages the account may send this month, a very large
        number when it has no limit, or None when LINE does not say."""
        quota = await self._get_json("/v2/bot/message/quota")
        if quota is None:
            return None
        if quota.get("type") != LIMITED_QUOTA:
            return UNLIMITED_MESSAGES
        used = await self._get_json("/v2/bot/message/quota/consumption")
        limit, total = quota.get("value"), (used or {}).get("totalUsage")
        if not _is_count(limit) or not _is_count(total):
            return None
        return max(0, limit - total)

    async def close(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    async def _get_json(self, path: str) -> dict[str, Any] | None:
        try:
            response = await self._http.get(path, headers=self._headers)
            body = response.json() if response.status_code == HTTP_OK else None
        except (httpx.HTTPError, ValueError):
            return None
        return body if isinstance(body, dict) else None

    async def _post(
        self,
        path: str,
        body: dict[str, object],
        action: str,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {**self._headers, **(extra_headers or {})}
        try:
            return await self._http.post(path, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise LineApiError(action, 0) from error


def _messages(
    text: str | None,
    cards: Sequence[Card],
    with_images: bool,
    quote_token: str | None,
    extras: Sequence[OutgoingExtra],
    quick_replies: Sequence[QuickReplyItem],
) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if text:
        message: dict[str, Any] = {"type": "text", "text": fit_text(text)}
        if quote_token:
            message["quoteToken"] = quote_token
        messages.append(message)
    if cards:
        messages.append(build_flex_message(list(cards), with_images=with_images))
    messages.extend(dict(extra.message) for extra in extras)
    if quick_replies and messages:
        messages[-1]["quickReply"] = build_quick_reply(quick_replies)
    return messages


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_token_refusal(response: httpx.Response) -> bool:
    """Tell a refused reply token from a refused message: both are a 400, and only
    the error's `message` differs. The body is read here and never logged."""
    try:
        message = response.json().get("message")
    except (ValueError, AttributeError):
        return False
    return isinstance(message, str) and TOKEN_REFUSED_MARKER in message.lower()


def fit_text(text: str) -> str:
    """Cut text to LINE's limit, which counts UTF-16 code units, not characters."""
    encoded = text.encode("utf-16-le")
    limit_bytes = TEXT_LIMIT_UTF16_UNITS * 2
    if len(encoded) <= limit_bytes:
        return text
    return encoded[:limit_bytes].decode("utf-16-le", errors="ignore")
