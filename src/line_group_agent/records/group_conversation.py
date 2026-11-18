"""The running state of one group's conversation, rebuilt from its record.

Holds the messages of the current generation (what is sent to the model), how much of
the context they fill, the generation number, and a summary that is waiting to open
the next generation. Called by the answerer, the rollover and the tab list.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent._common.context_usage import context_tokens_of
from line_group_agent.records.conversation_log import (
    SUMMARY_PREFIX,
    ConversationLog,
    record_name_of,
)


class GroupConversation:
    """One group's conversation: the record, the current generation and what waits."""

    def __init__(self, group_id: str, record_path: Path) -> None:
        self.group_id = group_id
        self.name = record_name_of(group_id)
        self.log = ConversationLog(record_path)
        self.lock = asyncio.Lock()
        self.title: str | None = None
        self.title_checked_at: datetime | None = None
        self.last_activity_at: datetime | None = None
        self.last_turn_message_id: str | None = None
        self.messages: list[dict[str, Any]] = []
        self.context_tokens: int | None = None
        self.generation = 1
        self.generation_started_at: str | None = None
        self.pending_summary: str | None = None
        self.pending_since: datetime | None = None

    def open(self) -> None:
        """Make the record ready to append and rebuild the state from its rows."""
        self.log.open()
        for row in self.log.read_rows():
            self._apply(row)

    @property
    def starts_new_generation(self) -> bool:
        """Whether the next user turn opens a generation (a summary waits, or no turn yet)."""
        return self.pending_summary is not None or not self.messages

    def history(self) -> list[dict[str, Any]]:
        """Return the messages to send ahead of the next user turn (none when it opens a
        new generation)."""
        return [] if self.starts_new_generation else list(self.messages)

    @property
    def shown_generation(self) -> int:
        """The generation the next answer belongs to (one more while a summary waits)."""
        return self.generation + (1 if self.pending_summary is not None else 0)

    @property
    def shown_context_tokens(self) -> int:
        """The context amount the rollover decision uses; 0 while a summary waits."""
        if self.pending_summary is not None:
            return 0
        return self.context_tokens or 0

    @property
    def last_rollover_at(self) -> str | None:
        """When the conversation last rolled over (ISO 8601), or None if it never did."""
        if self.pending_since is not None:
            return self.pending_since.isoformat(timespec="seconds")
        return self.generation_started_at

    def set_pending_summary(self, text: str, written_at: datetime) -> None:
        """Keep a summary that opens the next generation with the next user turn."""
        self.pending_summary = text
        self.pending_since = written_at

    def add_user(self, content: str | list[dict[str, Any]]) -> None:
        """Append a user turn to the record and the state."""
        self._apply(self.log.add_user(content))

    def add_assistant(self, answer: dict[str, Any]) -> None:
        """Append the API's answer (as it came) to the record and the state."""
        self._apply(self.log.add_assistant(answer))

    def _apply(self, row: dict[str, Any]) -> None:
        message = row.get("message")
        if not isinstance(message, dict):
            return
        if row.get("type") == "user":
            self._apply_user(message.get("content"), row.get("timestamp"))
        elif row.get("type") == "assistant":
            self.messages.append({"role": "assistant", "content": message.get("content") or []})
            usage = message.get("usage")
            if isinstance(usage, dict):
                self.context_tokens = context_tokens_of(usage)

    def _apply_user(self, content: Any, timestamp: Any) -> None:
        if isinstance(content, str) and content.startswith(SUMMARY_PREFIX):
            self.generation += 1 if self.messages else 0
            self.messages = []
            self.context_tokens = None
            self.generation_started_at = timestamp if isinstance(timestamp, str) else None
            self.pending_summary = None
            self.pending_since = None
        if isinstance(content, str | list):
            self.messages.append({"role": "user", "content": content})
