"""Delete messages from every place the agent keeps them: the group's record, the
conversation record and the running conversation.

Called by the answerer when the model runs `delete_messages` and by the event
dispatcher when a member unsends a message. The running conversation is rewritten
without the messages (and without its thinking blocks), and is marked to roll over at
once, so that the next conversation opens from a summary that is told not to repeat
them. The texts of what was deleted are handed to the summary scrubber, which takes them out of
the summaries that already exist. A message cannot be removed from the LINE chat itself.
"""

from __future__ import annotations

import logging

from line_group_agent.agent.message_redactor import redact_row
from line_group_agent.agent.summary_scrubber import SummaryScrubber
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog

logger = logging.getLogger(__name__)


class MessageDeleter:
    """Removes messages from the group's record and the conversation."""

    def __init__(
        self,
        group_log: GroupLog,
        conversations: GroupConversations,
        *,
        search_limit: int,
        scrubber: SummaryScrubber | None = None,
    ) -> None:
        self.group_log = group_log
        self.conversations = conversations
        self.search_limit = search_limit
        self.scrubber = scrubber

    def delete_matching(
        self,
        group_id: str,
        query: str,
        *,
        requester_user_id: str | None,
        request_message_id: str,
    ) -> int:
        """Delete the requester's own messages and the bot's replies that contain `query`
        (at most `search_limit`, newest first) and return how many were deleted.

        The caller holds the conversation's lock; the message that made the request
        stays.
        """
        found = self.group_log.list_deletable(
            group_id,
            query,
            self.search_limit,
            requester_user_id=requester_user_id,
            exclude_message_id=request_message_id,
        )
        return self.delete(group_id, {m.message_id for m in found})

    async def delete_unsent(self, group_id: str, message_id: str) -> int:
        """Delete a message its author took back, waiting for any answer or summary in
        progress, and return how many were deleted (0 when it was never recorded)."""
        conversation = self.conversations.get(group_id)
        async with conversation.lock:
            return self.delete(group_id, {message_id})

    def delete(self, group_id: str, message_ids: set[str]) -> int:
        """Delete the messages with these ids and return how many were found. The caller
        holds the conversation's lock."""
        removed = self.group_log.remove(group_id, message_ids)
        if not removed:
            return 0
        conversation = self.conversations.get(group_id)
        conversation.rewrite_rows(lambda row: redact_row(row, removed))
        if self.scrubber is not None:
            self.scrubber.note_deleted(group_id, removed)
        if conversation.messages:
            conversation.must_roll_over = True
        logger.info("delete: %d message(s) deleted from the records", len(removed))
        return len(removed)
