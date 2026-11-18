"""Deliver an answer to the group: by reply token if it still works, else by push.

The text and the cards are made plain first (LINE shows no Markdown), and the text can
quote the message that called the bot. Cards that LINE refuses are loosened step by step
(without images, then dropped) and a quote that LINE refuses is left out, so the text
still arrives. When a send fails for good the alert notifier is told. Called by the
event dispatcher; logs carry statuses only.
"""

from __future__ import annotations

import logging
from typing import Any

from line_group_agent.agent.answerer import Answer
from line_group_agent.agent.plain_text import to_plain_card, to_plain_text
from line_group_agent.alerts.alert_notifier import AlertNotifier
from line_group_agent.line_api.line_client import (
    HTTP_BAD_REQUEST,
    LineApiError,
    LineClient,
    ReplyResult,
)

logger = logging.getLogger(__name__)


class AnswerSender:
    """Sends one answer (text and cards) and reports what LINE accepted."""

    def __init__(self, line: LineClient, *, notifier: AlertNotifier | None = None) -> None:
        self.line = line
        self.notifier = notifier

    async def send(
        self,
        group_id: str,
        reply_token: Any,
        answer: Answer,
        *,
        quote_token: str | None = None,
    ) -> Answer | None:
        """Send the answer and return what was delivered, or None when nothing was.

        The returned answer is the plain one, and has no cards when they had to be
        dropped to get the text through. A push failure other than a refused card or a
        refused quote raises `LineApiError`.
        """
        plain = _plain(answer)
        # Push only when LINE refused the reply token; on any other failure the reply
        # may have been delivered, and a push would send the answer twice.
        cards = plain.cards
        if isinstance(reply_token, str) and reply_token:
            try:
                result = await self.line.reply(
                    reply_token, plain.text, cards, quote_token=quote_token
                )
                if result is ReplyResult.MESSAGE_REFUSED:
                    logger.info("reply: LINE refused the cards; trying once without images")
                    result = await self.line.reply(
                        reply_token, plain.text, cards, with_images=False, quote_token=quote_token
                    )
            except LineApiError as error:
                logger.warning("reply: failed (status %d); not retrying", error.status)
                await self._note_failure()
                return None
            if result is ReplyResult.SENT:
                return plain
            if result is ReplyResult.MESSAGE_REFUSED:
                logger.info("reply: LINE still refused the cards; sending the text only")
                cards = []
            else:
                logger.info("reply: the reply token was refused; sending by push instead")
        return await self._push(group_id, Answer(plain.text, cards), quote_token)

    async def _push(self, group_id: str, answer: Answer, quote_token: str | None) -> Answer | None:
        if not answer.text and not answer.cards:
            logger.info("answer: nothing left to send")
            return None
        try:
            await self.line.push(group_id, answer.text, answer.cards, quote_token=quote_token)
        except LineApiError as error:
            if error.status != HTTP_BAD_REQUEST or not (quote_token or answer.cards):
                await self._note_failure()
                raise
            if quote_token:
                logger.info("push: LINE refused the message; trying again without the quote")
                return await self._push(group_id, answer, None)
            logger.info("push: LINE refused the cards; sending the text only")
            if not answer.text:
                return None
            return await self._push(group_id, Answer(answer.text, []), None)
        return answer

    async def _note_failure(self) -> None:
        if self.notifier is not None:
            await self.notifier.note_send_failed()


def _plain(answer: Answer) -> Answer:
    text = None if answer.text is None else to_plain_text(answer.text)
    return Answer(text, [to_plain_card(card) for card in answer.cards])
