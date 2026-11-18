"""Every group's conversation the agent knows, opened from its record.

A group is known when it is on the configured list or already has a record in the
state folder, and from the moment the bot first handles one of its messages. The
number of known groups divides the monthly budget. Called by the answerer, the
rollover, the group watcher and the tab list.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from line_group_agent.records.conversation_log import record_name_of
from line_group_agent.records.group_conversation import GroupConversation
from line_group_agent.records.group_log import GROUP_ID_PATTERN, GroupLog
from line_group_agent.records.summary_journal import SummaryJournal


class GroupConversations:
    """Finds or opens the conversation of each group, one object per group."""

    def __init__(self, state_dir: Path, group_log: GroupLog, journal: SummaryJournal) -> None:
        self.state_dir = state_dir
        self.group_log = group_log
        self.journal = journal
        self._conversations: dict[str, GroupConversation] = {}

    def open(self, group_ids: Iterable[str]) -> None:
        """Open the conversations of the given groups and of every group with a record."""
        for group_id in sorted({*group_ids, *self.group_log.list_group_ids()}):
            self.get(group_id)

    def get(self, group_id: str) -> GroupConversation:
        """Return the group's conversation, opening it on first use."""
        if group_id not in self._conversations:
            self._conversations[group_id] = self._open_one(group_id)
        return self._conversations[group_id]

    def list(self) -> list[GroupConversation]:
        """Return the known conversations in record-name order."""
        return sorted(self._conversations.values(), key=lambda c: c.name)

    def count(self) -> int:
        """Return how many groups are known."""
        return len(self._conversations)

    def _open_one(self, group_id: str) -> GroupConversation:
        if not GROUP_ID_PATTERN.match(group_id):
            raise ValueError("a group id holds only letters and digits")
        record = self.state_dir / "conversations" / f"{record_name_of(group_id)}.jsonl"
        conversation = GroupConversation(group_id, record)
        conversation.open()
        waiting = self.journal.read(group_id, conversation.generation)
        if waiting is not None:
            conversation.set_pending_summary(*waiting)
        last_time = self.group_log.last_message_time(group_id)
        if last_time is not None:
            conversation.last_activity_at = _parse_time(last_time)
        return conversation


def _parse_time(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
