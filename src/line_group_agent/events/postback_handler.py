"""Count the votes that come in as postback events, without answering them.

A poll card's button sends `poll:<id>:<option index>` as a postback. The vote is written
to the poll book and nothing is sent back (no message is used up, and the group sees no
noise). LINE sends an event again when a delivery fails, and a second delivery of a press
would take the vote back, so an event id that was handled is skipped. A press that comes
without the member's id cannot be told from another member's, so it is not counted.
Called by the event dispatcher.
"""

from __future__ import annotations

import logging
from collections import deque

from line_group_agent.polls.poll_book import PollBook
from line_group_agent.polls.poll_message import POSTBACK_PREFIX, POSTBACK_SEPARATOR

logger = logging.getLogger(__name__)

SEEN_EVENT_COUNT = 1000


class PostbackHandler:
    """Turns postback data into votes."""

    def __init__(self, polls: PollBook) -> None:
        self.polls = polls
        self._seen: deque[str] = deque(maxlen=SEEN_EVENT_COUNT)

    def handle(
        self,
        group_id: str,
        *,
        data: str,
        user_id: str | None,
        display_name: str | None,
        event_id: str | None,
    ) -> None:
        """Count the vote in `data` if it is one; anything else is ignored."""
        parts = data.split(POSTBACK_SEPARATOR)
        if len(parts) != 3 or parts[0] != POSTBACK_PREFIX or not parts[2].isdigit():
            return
        if event_id is not None:
            if event_id in self._seen:
                logger.info("poll: a press that was already counted arrived again; skipped")
                return
            self._seen.append(event_id)
        if user_id is None:
            logger.info("poll: a press came without a user id; not counted")
            return
        result = self.polls.vote(group_id, parts[1], int(parts[2]), user_id, display_name)
        logger.info("poll: a vote was %s", result.value)
