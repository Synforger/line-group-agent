"""The record of a group: every text message of an allowed group, one JSON line each,
and every reply the bot sent there (marked `from_bot`), so a later mention sees the
conversation the bot itself took part in.

Written by the event dispatcher, read by the answerer (recent messages and history
search). Lives at `<state_dir>/groups/<groupId>/messages.jsonl`. Append only.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from line_group_agent.records._internal.jsonl import append_json_line, read_json_lines

GROUP_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{1,64}$")


@dataclass(frozen=True)
class GroupMessage:
    """One text message said in the group (by a member, or by the bot when `from_bot`)."""

    time: str
    message_id: str
    user_id: str | None
    display_name: str | None
    text: str
    from_bot: bool = False


class GroupLog:
    """Reads and appends the per-group message records under one state folder."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def add(self, group_id: str, message: GroupMessage) -> None:
        """Append one message to the group's record."""
        append_json_line(self._path(group_id), asdict(message))

    def has_message(self, group_id: str, message_id: str) -> bool:
        """Return whether a message with this id is already in the group's record."""
        return any(m.message_id == message_id for m in self._load(group_id))

    def list_recent(
        self, group_id: str, count: int, *, exclude_message_id: str | None = None
    ) -> list[GroupMessage]:
        """Return the last `count` messages, oldest first."""
        if count <= 0:
            return []
        messages = [m for m in self._load(group_id) if m.message_id != exclude_message_id]
        return messages[-count:]

    def list_since_turn(
        self,
        group_id: str,
        limit: int,
        *,
        after_message_id: str | None,
        exclude_message_id: str | None = None,
    ) -> list[GroupMessage]:
        """Return what the group said since the bot's last turn, oldest first.

        The last turn ends at the later of the bot's last reply and the message
        `after_message_id` (the mention the bot last took up, when known). The bot's
        own replies are left out, and at most the last `limit` messages are returned.
        """
        messages = self._load(group_id)
        cut = -1
        for index, message in enumerate(messages):
            if message.from_bot or message.message_id == after_message_id:
                cut = index
        since = [
            m for m in messages[cut + 1 :] if not m.from_bot and m.message_id != exclude_message_id
        ]
        return since[-limit:] if limit > 0 else []

    def last_message_time(self, group_id: str) -> str | None:
        """Return the time of the group's latest recorded message, or None."""
        messages = self._load(group_id)
        return messages[-1].time if messages else None

    def list_group_ids(self) -> list[str]:
        """Return the ids of the groups that have a record, in name order."""
        root = self.state_dir / "groups"
        if not root.is_dir():
            return []
        return sorted(
            folder.name
            for folder in root.iterdir()
            if GROUP_ID_PATTERN.match(folder.name) and (folder / "messages.jsonl").exists()
        )

    def search(self, group_id: str, query: str, limit: int) -> list[GroupMessage]:
        """Return messages whose text contains `query` (any case), newest first."""
        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return []
        found = [m for m in reversed(self._load(group_id)) if needle in m.text.casefold()]
        return found[:limit]

    def _path(self, group_id: str) -> Path:
        if not GROUP_ID_PATTERN.match(group_id):
            raise ValueError("a group id holds only letters and digits")
        return self.state_dir / "groups" / group_id / "messages.jsonl"

    def _load(self, group_id: str) -> list[GroupMessage]:
        messages: list[GroupMessage] = []
        for row in read_json_lines(self._path(group_id)):
            text = row.get("text")
            if not isinstance(text, str):
                continue
            messages.append(
                GroupMessage(
                    time=str(row.get("time", "")),
                    message_id=str(row.get("message_id", "")),
                    user_id=row.get("user_id"),
                    display_name=row.get("display_name"),
                    text=text,
                    from_bot=row.get("from_bot") is True,
                )
            )
        return messages
