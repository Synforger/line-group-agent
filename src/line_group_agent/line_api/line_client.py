"""The calls this agent makes to the LINE Messaging API: reply, push, member name.

Called by the event dispatcher. Errors carry the HTTP status only, never a token or
the text that was sent.
"""

from __future__ import annotations

import uuid

import httpx

API_BASE_URL = "https://api.line.me"
REQUEST_TIMEOUT_SECONDS = 15.0
TEXT_LIMIT_UTF16_UNITS = 5000
HTTP_OK = 200
HTTP_BAD_REQUEST = 400


class LineApiError(RuntimeError):
    """A LINE API call failed; `status` is the HTTP status (0 when no answer came)."""

    def __init__(self, action: str, status: int) -> None:
        super().__init__(f"LINE {action} failed with status {status}")
        self.status = status


class LineClient:
    """Sends text to a group and looks up a member's display name."""

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

    async def reply(self, reply_token: str, text: str) -> bool:
        """Answer an event with its reply token. Return False when LINE refuses the
        token (used, or too old) so the caller can push instead."""
        body = {"replyToken": reply_token, "messages": [_text_message(text)]}
        status = await self._post("/v2/bot/message/reply", body, "reply")
        if status == HTTP_OK:
            return True
        if status == HTTP_BAD_REQUEST:
            return False
        raise LineApiError("reply", status)

    async def push(self, to: str, text: str) -> None:
        """Send text to a group (counts against the account's monthly message quota)."""
        body = {"to": to, "messages": [_text_message(text)]}
        headers = {"X-Line-Retry-Key": str(uuid.uuid4())}
        status = await self._post("/v2/bot/message/push", body, "push", headers)
        if status != HTTP_OK:
            raise LineApiError("push", status)

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

    async def close(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()

    async def _post(
        self,
        path: str,
        body: dict[str, object],
        action: str,
        extra_headers: dict[str, str] | None = None,
    ) -> int:
        headers = {**self._headers, **(extra_headers or {})}
        try:
            response = await self._http.post(path, json=body, headers=headers)
        except httpx.HTTPError as error:
            raise LineApiError(action, 0) from error
        return response.status_code


def _text_message(text: str) -> dict[str, str]:
    return {"type": "text", "text": fit_text(text)}


def fit_text(text: str) -> str:
    """Cut text to LINE's limit, which counts UTF-16 code units, not characters."""
    encoded = text.encode("utf-16-le")
    limit_bytes = TEXT_LIMIT_UTF16_UNITS * 2
    if len(encoded) <= limit_bytes:
        return text
    return encoded[:limit_bytes].decode("utf-16-le", errors="ignore")
