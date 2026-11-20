"""What the voting page may do: open a poll and vote on it, for a member who proves who they
are.

Every call carries the member's LINE ID token. The member first passes the gate (the token is
verified and their requests are counted), the poll is found by the unguessable id of its link,
and the member must be in the poll's group; only then is the poll's content given. A refusal
is a `LiffRefusal` that carries an HTTP status and nothing else. Votes go to the same poll book
as the postback votes. Called by the LIFF router.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from line_group_agent.liff.liff_gate import LiffGate
from line_group_agent.liff.liff_members import LiffMembers
from line_group_agent.liff.liff_refusal import (
    HTTP_BAD_REQUEST,
    HTTP_FORBIDDEN,
    HTTP_UNAVAILABLE,
    LiffRefusal,
)
from line_group_agent.liff.poll_view import poll_view_of, unnamed_voter_ids
from line_group_agent.liff.request_limiter import RequestLimiter
from line_group_agent.liff.verify_failure_limiter import VerifyFailureLimiter
from line_group_agent.line_api.login_client import LoginClient
from line_group_agent.polls.poll_book import PollBook, PollLocation

logger = logging.getLogger(__name__)

NAME_LOOKUP_LIMIT = 20


class LiffPolls:
    """Opens and votes on polls for the voting page."""

    def __init__(
        self,
        polls: PollBook,
        login: LoginClient,
        members: LiffMembers,
        limiter: RequestLimiter,
        verify_failures: VerifyFailureLimiter,
        *,
        login_channel_id: str,
        is_group_allowed: Callable[[str], bool],
        clock: Callable[[], datetime],
    ) -> None:
        self.polls = polls
        self.gate = LiffGate(
            login, limiter, verify_failures, login_channel_id=login_channel_id, clock=clock
        )
        self.members = members
        self.is_group_allowed = is_group_allowed

    async def show(self, id_token: str, link_id: str, source: str | None) -> dict[str, Any]:
        """Return the poll of this link as the member sees it. `source` is the address the
        request came from, or None when it is not known."""
        user_id, location = await self._enter(id_token, link_id, source)
        return await self._view_of(location, user_id)

    async def vote(
        self, id_token: str, link_id: str, option_index: int, source: str | None
    ) -> dict[str, Any]:
        """Count the member's vote on an option of the poll and return the poll as it is then.
        A closed poll is returned unchanged."""
        user_id, location = await self._enter(id_token, link_id, source)
        poll = location.poll
        if not 0 <= option_index < len(poll.options):
            raise LiffRefusal(HTTP_BAD_REQUEST)
        name = await self.members.name_of(location.group_id, user_id)
        result = self.polls.vote(location.group_id, poll.id, option_index, user_id, name)
        logger.info("liff: a vote was %s", result.value)
        return await self._view_of(location, user_id)

    async def _enter(
        self, id_token: str, link_id: str, source: str | None
    ) -> tuple[str, PollLocation]:
        user_id = await self.gate.admit(id_token, source)
        location = self.polls.find_by_link_id(link_id)
        if location is None or not self.is_group_allowed(location.group_id):
            logger.info("liff: refused, no such poll")
            raise LiffRefusal(HTTP_FORBIDDEN)
        is_member = await self.members.is_member(location.group_id, user_id)
        if is_member is None:
            logger.warning("liff: refused, LINE did not say whether the member is in the group")
            raise LiffRefusal(HTTP_UNAVAILABLE)
        if not is_member:
            logger.info("liff: refused, not a member of the group")
            raise LiffRefusal(HTTP_FORBIDDEN)
        return user_id, location

    async def _view_of(self, location: PollLocation, user_id: str) -> dict[str, Any]:
        # Read the poll again: it may have changed while LINE was being asked.
        group_id = location.group_id
        poll = self.polls.get(group_id, location.poll.id) or location.poll
        unnamed = unnamed_voter_ids(poll)[:NAME_LOOKUP_LIMIT]
        names = await asyncio.gather(*(self.members.name_of(group_id, other) for other in unnamed))
        found = {other: name for other, name in zip(unnamed, names, strict=True) if name}
        return poll_view_of(poll, user_id, found)
