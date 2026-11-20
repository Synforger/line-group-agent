"""A request a LIFF page may not have, and the HTTP statuses its refusals carry.

Raised by the LIFF services (the gate, the polls, the itineraries) and answered by the LIFF
router, which turns the status into a bare one-word error.
"""

from __future__ import annotations

HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_FORBIDDEN = 403
HTTP_TOO_MANY_REQUESTS = 429
HTTP_UNAVAILABLE = 503


class LiffRefusal(Exception):
    """A request the page may not have; `status` is the HTTP status to answer with. It holds
    no detail on purpose: what was wrong is not told to the caller."""

    def __init__(self, status: int) -> None:
        super().__init__(f"refused with status {status}")
        self.status = status
