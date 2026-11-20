"""The door of a LIFF page: prove who the caller is and count their requests.

Every call carries the member's LINE ID token. It is verified with LINE Login (its audience and
expiry checked again here; while too many verifies have failed LINE is not asked at all), and
the member's requests are counted. A refusal is a `LiffRefusal` that carries an HTTP status and
nothing else. Called by the poll and itinerary services of the LIFF pages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from line_group_agent.liff.id_token_check import user_id_of_claims
from line_group_agent.liff.liff_refusal import (
    HTTP_TOO_MANY_REQUESTS,
    HTTP_UNAUTHORIZED,
    HTTP_UNAVAILABLE,
    LiffRefusal,
)
from line_group_agent.liff.request_limiter import RequestLimiter
from line_group_agent.liff.verify_failure_limiter import VerifyFailureLimiter
from line_group_agent.line_api.line_client import LineApiError
from line_group_agent.line_api.login_client import LoginClient

logger = logging.getLogger(__name__)


class LiffGate:
    """Lets a request through only for a member whose ID token is good and who is not over
    the request limit."""

    def __init__(
        self,
        login: LoginClient,
        limiter: RequestLimiter,
        verify_failures: VerifyFailureLimiter,
        *,
        login_channel_id: str,
        clock: Callable[[], datetime],
    ) -> None:
        self.login = login
        self.limiter = limiter
        self.verify_failures = verify_failures
        self.login_channel_id = login_channel_id
        self._clock = clock

    async def admit(self, id_token: str, source: str | None) -> str:
        """Return the id of the member the token belongs to and count the request. `source` is
        the address the request came from, or None when it is not known."""
        user_id = await self._verified_user(id_token, source)
        if not self.limiter.allow(user_id):
            logger.info("liff: refused, too many requests")
            raise LiffRefusal(HTTP_TOO_MANY_REQUESTS)
        return user_id

    async def _verified_user(self, id_token: str, source: str | None) -> str:
        blocked_by = self.verify_failures.blocked_by(source)
        if blocked_by is not None:
            logger.warning("liff: refused, too many failed verifies (%s limit)", blocked_by)
            raise LiffRefusal(HTTP_TOO_MANY_REQUESTS)
        try:
            claims = await self.login.verify_id_token(id_token, self.login_channel_id)
        except LineApiError as error:
            logger.warning("liff: LINE could not verify a token (status %d)", error.status)
            raise LiffRefusal(HTTP_UNAVAILABLE) from error
        user_id = (
            None
            if claims is None
            else user_id_of_claims(claims, self.login_channel_id, self._clock().timestamp())
        )
        if user_id is None:
            self.verify_failures.record_failure(source)
            logger.info("liff: refused, the token did not pass")
            raise LiffRefusal(HTTP_UNAUTHORIZED)
        return user_id
