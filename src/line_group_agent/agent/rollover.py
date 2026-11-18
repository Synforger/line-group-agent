"""Close a full conversation: ask the model for a summary, keep it in the group's
journal, and let it open the next generation with the next user turn.

Called by the group watcher, after an answer (the conversation is full enough) and at
each patrol (the group has been quiet for a long time). A conversation marked after a
message was deleted rolls over at the next call whatever its size, and its summary is
asked not to repeat what was deleted. The summary is made by one
extra request on top of the conversation, with no tools allowed, and is not added to
the conversation record; its cost counts against the group.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from line_group_agent._common.context_usage import is_idle_rollover_due, is_rollover_due
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import summary_request
from line_group_agent.agent.tool_pairing import pair_tool_calls
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.records.group_conversation import GroupConversation
from line_group_agent.records.summary_journal import SummaryJournal
from line_group_agent.spend.pricing import request_estimate_usd, to_currency
from line_group_agent.spend.spend_books import SpendBooks

logger = logging.getLogger(__name__)

NO_TOOLS = {"type": "none"}


class Rollover:
    """Rolls a group's conversation over when it is due."""

    def __init__(
        self,
        config: AgentConfig,
        caller: ModelCaller,
        journal: SummaryJournal,
        books: SpendBooks,
        settings: SettingsStore,
        clock: Callable[[], datetime],
    ) -> None:
        self.config = config
        self.caller = caller
        self.journal = journal
        self.books = books
        self.settings = settings
        self._clock = clock

    async def roll_over_if_full(self, conversation: GroupConversation) -> bool:
        """Roll the conversation over when its context reached `rollover_percent`.
        Return whether a summary was made."""
        return await self._roll_over(conversation, is_idle=False)

    async def roll_over_if_idle(self, conversation: GroupConversation) -> bool:
        """Roll the conversation over when the group has been quiet for `idle_hours` and
        the context reached `idle_rollover_percent`. Return whether a summary was made."""
        return await self._roll_over(conversation, is_idle=True)

    async def _roll_over(self, conversation: GroupConversation, *, is_idle: bool) -> bool:
        async with conversation.lock:
            if not self._is_due(conversation, is_idle=is_idle):
                return False
            summary = await self._summarize(conversation)
            if summary is None:
                return False
            now = self._clock()
            self.journal.write(conversation.group_id, conversation.generation, summary, now.date())
            conversation.set_pending_summary(summary, now)
            logger.info("rollover: generation %d summarized", conversation.generation)
            return True

    def _is_due(self, conversation: GroupConversation, *, is_idle: bool) -> bool:
        if conversation.pending_summary is not None or not conversation.messages:
            return False
        if conversation.must_roll_over:
            return True
        if conversation.context_tokens is None:
            return False
        settings = self.settings.current()
        if is_idle:
            return is_idle_rollover_due(
                conversation.context_tokens, conversation.last_activity_at, self._clock(), settings
            )
        return is_rollover_due(conversation.context_tokens, settings)

    async def _summarize(self, conversation: GroupConversation) -> str | None:
        group_id = conversation.group_id
        estimate = request_estimate_usd(
            self.config,
            context_tokens=conversation.context_tokens,
            max_tokens=self.config.summary_max_tokens,
            with_searches=False,
        )
        if not self.books.can_afford(group_id, to_currency(estimate, self.config.budget)):
            logger.info("rollover: budget left is below one summary; not calling the API")
            return None
        messages = pair_tool_calls(
            [
                *conversation.messages,
                {
                    "role": "user",
                    "content": summary_request(after_deletion=conversation.must_roll_over),
                },
            ]
        )
        answer = await self.caller.create(
            group_id,
            messages,
            max_tokens=self.config.summary_max_tokens,
            tool_choice=NO_TOOLS,
        )
        if answer is None:
            return None
        blocks = answer.get("content") or []
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text").strip()
        if not text:
            logger.warning("rollover: the summary came back empty")
            return None
        return text
