"""The one call this agent makes to LINE Login: checking an ID token.

The voting page sends the member's ID token with each request; LINE says whether it is genuine
and what it holds. Called by the LIFF poll service. Errors carry the HTTP status only, never
the token.
"""

from __future__ import annotations

from typing import Any

import httpx

from line_group_agent.line_api.line_client import (
    API_BASE_URL,
    HTTP_BAD_REQUEST,
    HTTP_OK,
    REQUEST_TIMEOUT_SECONDS,
    LineApiError,
)

VERIFY_PATH = "/oauth2/v2.1/verify"


class LoginClient:
    """Asks LINE Login to verify ID tokens."""

    def __init__(
        self, *, http_client: httpx.AsyncClient | None = None, base_url: str | None = None
    ) -> None:
        # trust_env=False: no proxy or certificate settings from environment variables.
        # A missing address is LINE's own; the settings may name another one (a stand-in).
        self._http = http_client or httpx.AsyncClient(
            base_url=base_url or API_BASE_URL, timeout=REQUEST_TIMEOUT_SECONDS, trust_env=False
        )

    async def verify_id_token(self, id_token: str, client_id: str) -> dict[str, Any] | None:
        """Return the claims LINE reads from the token, or None when LINE refuses it (a bad
        signature, a token of another channel, an expired one). Raises `LineApiError` when
        LINE gives no clear answer (an error status, or no connection)."""
        try:
            response = await self._http.post(
                VERIFY_PATH, data={"id_token": id_token, "client_id": client_id}
            )
        except httpx.HTTPError as error:
            raise LineApiError("verify", 0) from error
        if response.status_code == HTTP_BAD_REQUEST:
            return None
        if response.status_code != HTTP_OK:
            raise LineApiError("verify", response.status_code)
        try:
            claims = response.json()
        except ValueError:
            return None
        return claims if isinstance(claims, dict) else None

    async def close(self) -> None:
        """Close the HTTP connection pool."""
        await self._http.aclose()
