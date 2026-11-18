"""The tab list a chat client reads: one tab per group with its conversation record,
context amount, month's spend and generation, and the table of settings fields.

Written by the group watcher whenever something that it shows changes. The file is
replaced whole each time (a temporary file, then a rename) and only when its content
changed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent._common.atomic_write import write_text_atomically
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.records.group_conversation import GroupConversation
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.spend.spend_books import SpendBooks
from line_group_agent.tabs.settings_fields import SETTINGS_FIELDS


class TabsFile:
    """Keeps `tabs.json` in step with the groups the agent knows."""

    def __init__(
        self,
        path: Path,
        conversations: GroupConversations,
        books: SpendBooks,
        settings: SettingsStore,
        clock: Callable[[], datetime],
    ) -> None:
        self.path = path
        self.conversations = conversations
        self.books = books
        self.settings = settings
        self._clock = clock
        self._written: str | None = None

    def refresh(self) -> None:
        """Write the file when what it shows has changed since the last write."""
        content = {
            "settings_fields": SETTINGS_FIELDS,
            "context_window": self.settings.current().context_window_tokens,
            "tabs": [self._tab_of(c) for c in self.conversations.list()],
        }
        shown = json.dumps(content, ensure_ascii=False)
        if shown == self._written:
            return
        document = {"updated_at": self._clock().isoformat(timespec="seconds"), **content}
        write_text_atomically(self.path, json.dumps(document, ensure_ascii=False))
        self._written = shown

    def _tab_of(self, conversation: GroupConversation) -> dict[str, Any]:
        return {
            "name": conversation.name,
            "title": conversation.title or conversation.name,
            "record": str(conversation.log.path),
            "context_tokens": conversation.shown_context_tokens,
            "spend": self.books.group_figure(conversation.group_id),
            "generation": conversation.shown_generation,
            "last_rollover_at": conversation.last_rollover_at,
        }
