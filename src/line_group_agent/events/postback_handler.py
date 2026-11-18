"""Count the votes that come in as postback events and say what line, if any, answers them.

A poll card's button sends `poll:<id>:<option index>` as a postback. The vote is written
to the poll book. A one-pick poll gets no answer here: its button already shows the choice
in the talk (see the poll message). A poll that allows several picks (a date poll too) gets
one line back, naming the member and what they now have picked, because pressing is a
switch and nothing else shows which way it went. LINE sends an event again when a delivery
fails, and a second delivery of a press would flip the switch back, so an event id that was
handled is skipped. A press that comes without the member's id cannot be told from another
member's, so it is not counted. Called by the event dispatcher, which sends the line.
"""

from __future__ import annotations

import logging
from collections import deque

from line_group_agent.polls.poll_book import PollBook, VoteResult
from line_group_agent.polls.poll_message import POSTBACK_PREFIX, POSTBACK_SEPARATOR
from line_group_agent.polls.poll_text import format_picks_line

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
    ) -> str | None:
        """Count the vote in `data` if it is one (anything else is ignored). Return the line
        to answer the member with, or None when no answer is due."""
        parts = data.split(POSTBACK_SEPARATOR)
        if len(parts) != 3 or parts[0] != POSTBACK_PREFIX or not parts[2].isdigit():
            return None
        if event_id is not None:
            if event_id in self._seen:
                logger.info("poll: a press that was already counted arrived again; skipped")
                return None
            self._seen.append(event_id)
        if user_id is None:
            logger.info("poll: a press came without a user id; not counted")
            return None
        result = self.polls.vote(group_id, parts[1], int(parts[2]), user_id, display_name)
        logger.info("poll: a vote was %s", result.value)
        if result not in (VoteResult.COUNTED, VoteResult.WITHDRAWN):
            return None
        poll = self.polls.get(group_id, parts[1])
        if poll is None or not poll.multiple:
            return None
        return format_picks_line(poll, user_id, display_name)
