"""The running state of one group's conversation, rebuilt from its record.

Holds the messages of the current generation (what is sent to the model), how much of
the context they fill, the generation number, and a summary that is waiting to open
the next generation. Called by the answerer, the rollover, the message deleter, the
retention sweeper and the tab list.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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
        self.must_roll_over = False
        self._opening_content: str | None = None
        self._opened_at: str | None = None

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

    @property
    def live_since(self) -> datetime | None:
        """When the running generation's first row was written, or None when no
        generation is running (the record is empty, or a summary waits to open the next)."""
        if self._opened_at is None or self.pending_summary is not None:
            return None
        return datetime.fromisoformat(self._opened_at)

    def has_opened_with(self, summary: str) -> bool:
        """Whether the running generation opened with this summary (so it has been used)."""
        opening = f"{SUMMARY_PREFIX}\n{summary.strip()}\n\n"
        return self._opening_content is not None and self._opening_content.startswith(opening)

    def set_pending_summary(self, text: str, written_at: datetime) -> None:
        """Keep a summary that opens the next generation with the next user turn."""
        self.pending_summary = text
        self.pending_since = written_at
        self.must_roll_over = False

    def add_user(self, content: str | list[dict[str, Any]]) -> None:
        """Append a user turn to the record and the state."""
        self._apply(self.log.add_user(content))

    def add_assistant(self, answer: dict[str, Any]) -> None:
        """Append the API's answer (as it came) to the record and the state."""
        self._apply(self.log.add_assistant(answer))

    def rewrite_rows(self, change: Callable[[dict[str, Any]], dict[str, Any] | None]) -> None:
        """Replace each row of the record by `change(row)` (a row dropped when it returns
        None), write the record whole and rebuild the state from it."""
        rows = (change(row) for row in self.log.read_rows())
        self.log.replace_rows([row for row in rows if row is not None])
        self._rebuild()

    def drop_rows_before(self, cutoff: datetime) -> int:
        """Delete the rows written before `cutoff` that do not belong to the running
        generation, and return how many went. Rows of the running generation stay."""
        live_since = self.live_since

        def is_expired(row: dict[str, Any]) -> bool:
            written_at = _moment_of(row.get("timestamp"))
            if written_at is None or written_at >= cutoff:
                return False
            return live_since is None or written_at < live_since

        expired = sum(1 for row in self.log.read_rows() if is_expired(row))
        if expired:
            self.rewrite_rows(lambda row: None if is_expired(row) else row)
        return expired

    def _rebuild(self) -> None:
        generation, started_at = self.generation, self.generation_started_at
        waiting = (self.pending_summary, self.pending_since)
        self.messages = []
        self.context_tokens = None
        self.pending_summary = None
        self.pending_since = None
        self._opening_content = None
        self._opened_at = None
        for row in self.log.read_rows():
            self._apply(row)
        # Rewriting rows does not change which generation this is, nor a waiting summary.
        self.generation, self.generation_started_at = generation, started_at
        if self.pending_summary is None:
            self.pending_summary, self.pending_since = waiting

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
        text = _leading_text_of(content)
        if text is not None and text.startswith(SUMMARY_PREFIX):
            self.generation += 1 if self.messages else 0
            self.messages = []
            self.context_tokens = None
            self.generation_started_at = timestamp if isinstance(timestamp, str) else None
            self.pending_summary = None
            self.pending_since = None
        if not self.messages and isinstance(timestamp, str):
            self._opened_at = timestamp
            self._opening_content = text
        if isinstance(content, str | list):
            self.messages.append({"role": "user", "content": content})


def _moment_of(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _leading_text_of(content: Any) -> str | None:
    """Return the text of a user turn: the string itself, or the first text block of a turn
    that carries photos after its text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content and isinstance(content[0], dict):
        text = content[0].get("text")
        return text if content[0].get("type") == "text" and isinstance(text, str) else None
    return None
