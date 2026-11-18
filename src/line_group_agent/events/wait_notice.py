"""Tell the group "one moment" while a slow answer is being worked out.

Called by the event dispatcher when the answerer says the answer will take a while. The
notice uses the event's reply token, so the answer itself then goes out by push; that
costs one message of the account's monthly quota, so the notice is skipped when LINE
does not say how many are left or fewer than `min_push_left` remain.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from line_group_agent.cards.card import Card
from line_group_agent.line_api.line_client import LineApiError, ReplyResult
from line_group_agent.line_api.push_quota import PushQuota

logger = logging.getLogger(__name__)


class NoticeLine(Protocol):
    """What the notice needs from the LINE client: a reply."""

    async def reply(
        self, reply_token: str, text: str | None, cards: Sequence[Card] = ()
    ) -> ReplyResult: ...


class WaitNotice:
    """Sends the fixed wait text through a reply token when pushes are to spare."""

    def __init__(
        self, line: NoticeLine, quota: PushQuota, text: str, *, min_push_left: int
    ) -> None:
        self.line = line
        self.quota = quota
        self.text = text
        self.min_push_left = min_push_left

    async def send(self, reply_token: object) -> bool:
        """Send the notice and return whether it went out, so the reply token is used up."""
        if not self.text or not isinstance(reply_token, str) or not reply_token:
            return False
        left = await self.quota.remaining()
        if left is None or left < self.min_push_left:
            logger.info("wait: not sent (messages left: %s)", "unknown" if left is None else left)
            return False
        try:
            result = await self.line.reply(reply_token, self.text)
        except LineApiError as error:
            logger.warning("wait: the notice failed (status %d)", error.status)
            return False
        return result is ReplyResult.SENT
