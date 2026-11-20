"""Deliver an answer to the group: by reply token if it still works, else by push.

The text and the cards are made plain first (LINE shows no Markdown), and the text can
quote the message that called the bot. A `<mention>name</mention>` mark in the text becomes
a real mention when the name is one a member of the group has in the group's record.
Cards, extra messages, quick replies and mentions that LINE refuses are loosened step by step
(cards without images and the mentions as plain names, then everything but the text dropped)
and a quote that LINE refuses is left out, so the text still arrives. When a send fails for
good the alert notifier is told. Called by the event dispatcher; logs carry statuses only.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from line_group_agent.agent.answerer import Answer
from line_group_agent.agent.plain_text import to_plain_card, to_plain_text
from line_group_agent.alerts.alert_notifier import AlertNotifier
from line_group_agent.events.group_speakers import speakers_of
from line_group_agent.line_api.line_client import (
    HTTP_BAD_REQUEST,
    TEXT_LIMIT_UTF16_UNITS,
    LineApiError,
    LineClient,
    ReplyResult,
)
from line_group_agent.line_api.mention_text import build_text_v2, has_mention_marks
from line_group_agent.records.group_log import GroupLog

logger = logging.getLogger(__name__)

# How far back in the group's record the names of the members who may be mentioned are read.
SPEAKER_LOOKUP_MESSAGES = 1000


class AnswerSender:
    """Sends one answer (text and cards) and reports what LINE accepted."""

    def __init__(
        self,
        line: LineClient,
        *,
        notifier: AlertNotifier | None = None,
        group_log: GroupLog | None = None,
    ) -> None:
        self.line = line
        self.notifier = notifier
        self.group_log = group_log

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
        extras = plain.extras
        quick_replies = plain.quick_replies
        mentionable = self._mentionable(group_id, plain.text)
        if isinstance(reply_token, str) and reply_token:
            try:
                result = await self.line.reply(
                    reply_token,
                    plain.text,
                    cards,
                    quote_token=quote_token,
                    extras=extras,
                    quick_replies=quick_replies,
                    mentionable=mentionable,
                )
                if result is ReplyResult.MESSAGE_REFUSED:
                    logger.info(
                        "reply: LINE refused the message; trying once without images or mentions"
                    )
                    mentionable = {}
                    result = await self.line.reply(
                        reply_token,
                        plain.text,
                        cards,
                        with_images=False,
                        quote_token=quote_token,
                        extras=extras,
                        quick_replies=quick_replies,
                    )
            except LineApiError as error:
                logger.warning("reply: failed (status %d); not retrying", error.status)
                await self._note_failure()
                return None
            if result is ReplyResult.SENT:
                return plain
            if result is ReplyResult.MESSAGE_REFUSED:
                logger.info("reply: LINE still refused the message; sending the text only")
                cards, extras, quick_replies = [], [], []
            else:
                logger.info("reply: the reply token was refused; sending by push instead")
        return await self._push(
            group_id,
            Answer(plain.text, cards, extras=extras, quick_replies=quick_replies),
            quote_token,
            mentionable,
        )

    async def _push(
        self,
        group_id: str,
        answer: Answer,
        quote_token: str | None,
        mentionable: Mapping[str, str] | None = None,
    ) -> Answer | None:
        if not answer.text and not answer.cards and not answer.extras:
            logger.info("answer: nothing left to send")
            return None
        try:
            await self.line.push(
                group_id,
                answer.text,
                answer.cards,
                quote_token=quote_token,
                extras=answer.extras,
                quick_replies=answer.quick_replies,
                mentionable=mentionable,
            )
        except LineApiError as error:
            is_rich = bool(
                answer.cards
                or answer.extras
                or answer.quick_replies
                or _is_mentioning(answer.text, mentionable)
            )
            if error.status != HTTP_BAD_REQUEST or not (quote_token or is_rich):
                await self._note_failure()
                raise
            if quote_token:
                logger.info("push: LINE refused the message; trying again without the quote")
                return await self._push(group_id, answer, None, mentionable)
            logger.info("push: LINE refused the cards, extras or mentions; sending the text only")
            if not answer.text:
                return None
            return await self._push(group_id, Answer(answer.text, []), None)
        return answer

    def _mentionable(self, group_id: str, text: str | None) -> dict[str, str]:
        """Return the members the text may mention: each name the group's record holds for
        exactly one member, to that member's user id. Empty when the text has no mention mark."""
        if self.group_log is None or not text or not has_mention_marks(text):
            return {}
        recent = self.group_log.list_recent(group_id, SPEAKER_LOOKUP_MESSAGES)
        return speakers_of(recent)

    async def _note_failure(self) -> None:
        if self.notifier is not None:
            await self.notifier.note_send_failed()


def _is_mentioning(text: str | None, mentionable: Mapping[str, str] | None) -> bool:
    if not text or not mentionable:
        return False
    return build_text_v2(text, mentionable, limit_utf16_units=TEXT_LIMIT_UTF16_UNITS) is not None


def _plain(answer: Answer) -> Answer:
    text = None if answer.text is None else to_plain_text(answer.text)
    return Answer(
        text,
        [to_plain_card(card) for card in answer.cards],
        extras=answer.extras,
        quick_replies=answer.quick_replies,
    )
