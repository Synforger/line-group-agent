"""Deliver an answer to the group: by reply token if it still works, else by push.

Cards that LINE refuses are loosened step by step (without images, then dropped) so
the text still arrives. Called by the event dispatcher; logs carry statuses only.
"""

from __future__ import annotations

import logging
from typing import Any

from line_group_agent.agent.answerer import Answer
from line_group_agent.line_api.line_client import (
    HTTP_BAD_REQUEST,
    LineApiError,
    LineClient,
    ReplyResult,
)

logger = logging.getLogger(__name__)


class AnswerSender:
    """Sends one answer (text and cards) and reports what LINE accepted."""

    def __init__(self, line: LineClient) -> None:
        self.line = line

    async def send(self, group_id: str, reply_token: Any, answer: Answer) -> Answer | None:
        """Send the answer and return what was delivered, or None when nothing was.

        The returned answer has no cards when they had to be dropped to get the text
        through. A push failure other than a refused card raises `LineApiError`.
        """
        # Push only when LINE refused the reply token; on any other failure the reply
        # may have been delivered, and a push would send the answer twice.
        cards = answer.cards
        if isinstance(reply_token, str) and reply_token:
            try:
                result = await self.line.reply(reply_token, answer.text, cards)
                if result is ReplyResult.MESSAGE_REFUSED:
                    logger.info("reply: LINE refused the cards; trying once without images")
                    result = await self.line.reply(
                        reply_token, answer.text, cards, with_images=False
                    )
            except LineApiError as error:
                logger.warning("reply: failed (status %d); not retrying", error.status)
                return None
            if result is ReplyResult.SENT:
                return answer
            if result is ReplyResult.MESSAGE_REFUSED:
                logger.info("reply: LINE still refused the cards; sending the text only")
                cards = []
            else:
                logger.info("reply: the reply token was refused; sending by push instead")
        return await self._push(group_id, Answer(answer.text, cards))

    async def _push(self, group_id: str, answer: Answer) -> Answer | None:
        if answer.text is None and not answer.cards:
            logger.info("answer: nothing left to send")
            return None
        try:
            await self.line.push(group_id, answer.text, answer.cards)
        except LineApiError as error:
            if not answer.cards or error.status != HTTP_BAD_REQUEST:
                raise
            logger.info("push: LINE refused the cards; sending the text only")
            if answer.text is None:
                return None
            await self.line.push(group_id, answer.text)
            return Answer(answer.text, [])
        return answer
