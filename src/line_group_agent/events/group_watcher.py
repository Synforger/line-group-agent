"""Keeps what the agent knows about each group current, around the events.

Called by the event dispatcher for each recorded message and after each answer, and by
the patrol at an interval. It registers a group when it first speaks, looks up the
group's name, notes when the group last spoke, rolls full or long-quiet conversations
over, re-reads the settings file and rewrites the tab list.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from line_group_agent.agent.rollover import Rollover
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.records.group_conversation import GroupConversation
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupMessage
from line_group_agent.tabs.tabs_file import TabsFile

logger = logging.getLogger(__name__)

TITLE_RECHECK = timedelta(hours=1)


class GroupNames(Protocol):
    """What the watcher needs from the LINE client: a group's name."""

    async def get_group_name(self, group_id: str) -> str | None: ...


class GroupWatcher:
    """Registers groups, rolls conversations over and keeps the tab list written."""

    def __init__(
        self,
        conversations: GroupConversations,
        tabs: TabsFile,
        names: GroupNames,
        rollover: Rollover,
        settings: SettingsStore,
        clock: Callable[[], datetime],
    ) -> None:
        self.conversations = conversations
        self.tabs = tabs
        self.names = names
        self.rollover = rollover
        self.settings = settings
        self._clock = clock

    async def note_message(self, group_id: str, message: GroupMessage) -> None:
        """Note that the group said something just now."""
        conversation = self.conversations.get(group_id)
        conversation.last_activity_at = _time_of(message.time) or self._clock()
        await self._update_title(conversation)
        self.tabs.refresh()

    async def after_answer(self, group_id: str) -> None:
        """Roll the group's conversation over if the answer filled it, then rewrite the
        tab list."""
        conversation = self.conversations.get(group_id)
        self.tabs.refresh()
        if await self.rollover.roll_over_if_full(conversation):
            self.tabs.refresh()

    async def patrol(self) -> None:
        """One round over every known group: names, long-quiet rollovers, the tab list."""
        for conversation in self.conversations.list():
            await self._update_title(conversation)
            await self.rollover.roll_over_if_idle(conversation)
        self.tabs.refresh()

    async def _update_title(self, conversation: GroupConversation) -> None:
        now = self._clock()
        checked = conversation.title_checked_at
        if conversation.title is not None and checked is not None and now - checked < TITLE_RECHECK:
            return
        conversation.title_checked_at = now
        title = await self.names.get_group_name(conversation.group_id)
        if title is not None:
            conversation.title = title


def _time_of(text: str) -> datetime | None:
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None
