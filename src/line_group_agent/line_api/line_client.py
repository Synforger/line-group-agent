"""The calls this agent makes to the LINE Messaging API: reply, push, member name,
membership check and leaving a group.

A reply or push carries the answer's text and, after it, one Flex Message holding the
cards (LINE takes up to 5 messages per call; this sends at most 2). Called by the
answer sender. Errors carry the HTTP status only, never a token or what was sent.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

import httpx

from line_group_agent.cards.card import Card
from line_group_agent.line_api.flex_cards import build_flex_message

API_BASE_URL = "https://api.line.me"
REQUEST_TIMEOUT_SECONDS = 15.0
TEXT_LIMIT_UTF16_UNITS = 5000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
TOKEN_REFUSED_MARKER = "reply token"


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
    ) -> ReplyResult:
        """Answer an event with its reply token: the text first, then the cards.

        `TOKEN_REFUSED` means the token was used or too old, so the caller can push.
        `MESSAGE_REFUSED` means LINE took the token but not the message, which only
        happens when cards were sent: the caller may try the cards without images.
        A 400 on a text-only reply is always reported as a refused token.
        """
        body = {"replyToken": reply_token, "messages": _messages(text, cards, with_images)}
        response = await self._post("/v2/bot/message/reply", body, "reply")
        if response.status_code == HTTP_OK:
            return ReplyResult.SENT
        if response.status_code == HTTP_BAD_REQUEST:
            if cards and not _is_token_refusal(response):
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
    ) -> None:
        """Send the text, then the cards, to a group (counts against the account's
        monthly message quota)."""
        body = {"to": to, "messages": _messages(text, cards, with_images)}
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

    async def close(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

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


def _messages(text: str | None, cards: Sequence[Card], with_images: bool) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []
    if text:
        messages.append({"type": "text", "text": fit_text(text)})
    if cards:
        messages.append(build_flex_message(list(cards), with_images=with_images))
    return messages


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
