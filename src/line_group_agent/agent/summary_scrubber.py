"""Take what a member had deleted out of the summaries too.

A summary the model wrote earlier may quote a message that was deleted afterwards. When
messages are deleted, their text is noted here; after the answer (or the unsend) is done,
every summary of the group that holds one of those texts word for word is rewritten by the
model without it, and the waiting summary and the opening row of the conversation record are
kept the same as the file. If the model cannot be asked (the budget, the API) or its text
still holds a deleted text, the text is replaced by `[deleted]` in code, so the content is
gone either way. A message shorter than `MIN_SCRUBBED_CHARS` is not searched for, since it
would match anything. The deleted texts are kept in memory only, never written to a file.

Called by the message deleter (what was deleted) and the group watcher (when to rewrite).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import DELETED_MARK, scrub_request
from line_group_agent.agent.rollover import NO_TOOLS
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.records.conversation_log import SUMMARY_PREFIX
from line_group_agent.records.group_conversation import GroupConversation
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupMessage
from line_group_agent.records.summary_journal import SummaryJournal
from line_group_agent.spend.pricing import request_estimate_usd, to_currency
from line_group_agent.spend.spend_books import SpendBooks

logger = logging.getLogger(__name__)

MIN_SCRUBBED_CHARS = 4


class SummaryScrubber:
    """Rewrites summaries that quote deleted messages."""

    def __init__(
        self,
        config: AgentConfig,
        caller: ModelCaller,
        journal: SummaryJournal,
        conversations: GroupConversations,
        books: SpendBooks,
    ) -> None:
        self.config = config
        self.caller = caller
        self.journal = journal
        self.conversations = conversations
        self.books = books
        self._pending: dict[str, list[str]] = {}

    def note_deleted(self, group_id: str, messages: Sequence[GroupMessage]) -> None:
        """Remember the texts of deleted messages until `scrub_pending` runs (a photo has no
        text of its own, and a text under `MIN_SCRUBBED_CHARS` is too short to look for)."""
        texts = [
            m.text.strip()
            for m in messages
            if not m.image_file and len(m.text.strip()) >= MIN_SCRUBBED_CHARS
        ]
        if texts:
            self._pending.setdefault(group_id, []).extend(texts)

    async def scrub_pending(self, group_id: str) -> int:
        """Rewrite every summary of the group that holds a noted text and return how many
        were rewritten. Waits for any answer in progress."""
        texts = self._pending.pop(group_id, [])
        if not texts:
            return 0
        conversation = self.conversations.get(group_id)
        rewritten_count = 0
        async with conversation.lock:
            for path in self.journal.list_paths(group_id):
                summary = path.read_text(encoding="utf-8").strip()
                found = [text for text in texts if text in summary]
                if not found:
                    continue
                rewritten = await self._rewrite(group_id, summary, found)
                self.journal.rewrite(path, rewritten)
                _follow_in_conversation(conversation, summary, rewritten.strip())
                rewritten_count += 1
        if rewritten_count:
            logger.info("scrub: %d summary(ies) rewritten after a deletion", rewritten_count)
        return rewritten_count

    async def _rewrite(self, group_id: str, summary: str, found: list[str]) -> str:
        text = await self._ask(group_id, summary, found) or summary
        for deleted in found:
            text = text.replace(deleted, DELETED_MARK)
        return text

    async def _ask(self, group_id: str, summary: str, found: list[str]) -> str | None:
        estimate = request_estimate_usd(
            self.config,
            max_tokens=self.config.summary_max_tokens,
            with_searches=False,
        )
        if not self.books.can_afford(group_id, to_currency(estimate, self.config.budget)):
            logger.info("scrub: budget left is below one rewrite; replacing the text in code")
            return None
        answer = await self.caller.create(
            group_id,
            [{"role": "user", "content": scrub_request(summary, found)}],
            max_tokens=self.config.summary_max_tokens,
            tool_choice=NO_TOOLS,
        )
        if answer is None:
            return None
        blocks = answer.get("content") or []
        text = "\n".join(b["text"] for b in blocks if b.get("type") == "text").strip()
        return text or None


def _follow_in_conversation(conversation: GroupConversation, old: str, new: str) -> None:
    """Keep the waiting summary and the opening row of the conversation the same as the file."""
    waiting = conversation.pending_summary
    if waiting is not None and waiting.strip() == old:
        conversation.pending_summary = new
    if any(_holds(row, old) for row in conversation.log.read_rows()):
        conversation.rewrite_rows(lambda row: _with_summary(row, old, new))


def _holds(row: dict[str, Any], summary: str) -> bool:
    text = _opening_text_of(row)
    return text is not None and text.startswith(SUMMARY_PREFIX) and summary in text


def _with_summary(row: dict[str, Any], old: str, new: str) -> dict[str, Any]:
    if not _holds(row, old):
        return row
    message = row["message"]
    content = message["content"]
    if isinstance(content, str):
        return {**row, "message": {**message, "content": content.replace(old, new)}}
    first = {**content[0], "text": content[0]["text"].replace(old, new)}
    return {**row, "message": {**message, "content": [first, *content[1:]]}}


def _opening_text_of(row: dict[str, Any]) -> str | None:
    message = row.get("message")
    if row.get("type") != "user" or not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text")
        return text if isinstance(text, str) else None
    return None
