"""The record of a group: every text message of an allowed group (and a line for each photo
or location), one JSON line each, and every reply the bot sent there (marked `from_bot`), so
a later mention sees the conversation the bot itself took part in.

Written by the event dispatcher, read by the answerer (recent messages and history
search). Lives at `<state_dir>/groups/<groupId>/messages.jsonl`. Rows are appended; the
file is rewritten whole only to delete messages (on request or by age) or to put in
messages imported from an old chat history; the photo files of deleted messages go with them.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from line_group_agent.records._internal.jsonl import (
    append_json_line,
    read_json_lines,
    replace_json_lines,
)

GROUP_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{1,64}$")
IMAGES_FOLDER_NAME = "images"


@dataclass(frozen=True)
class GroupMessage:
    """One message said in the group (by a member, or by the bot when `from_bot`). A photo
    is the text `[写真]` with the name of its file in `image_file`. A message put in from an
    old chat history has `imported` set; age never deletes it."""

    time: str
    message_id: str
    user_id: str | None
    display_name: str | None
    text: str
    from_bot: bool = False
    image_file: str | None = None
    imported: bool = False


class GroupLog:
    """Reads and appends the per-group message records under one state folder."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def add(self, group_id: str, message: GroupMessage) -> None:
        """Append one message to the group's record."""
        append_json_line(self._path(group_id), _row_of(message))

    def add_imported(self, group_id: str, messages: Sequence[GroupMessage]) -> int:
        """Put messages from an old chat history into the record in time order, leaving out
        any the record already holds (the same minute, name and text), and return how many
        were put in. The file is replaced whole, so no answer may be running."""
        path = self._path(group_id)
        rows = read_json_lines(path)
        known = Counter(_same_message_key(row) for row in rows)
        new: list[dict[str, Any]] = []
        for message in sorted(
            messages, key=lambda m: _moment_of(m.time) or datetime.min.astimezone()
        ):
            key = _same_message_key(_row_of(message))
            if known[key] > 0:
                known[key] -= 1
            else:
                new.append(_row_of(message))
        if new:
            replace_json_lines(path, _merged(rows, new))
        return len(new)

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

    def list_deletable(
        self,
        group_id: str,
        query: str,
        limit: int,
        *,
        requester_user_id: str | None,
        exclude_message_id: str | None = None,
    ) -> list[GroupMessage]:
        """Return the messages `query` finds that the requester may have deleted: their
        own, and the bot's replies. Newest first, at most `limit`; the message
        `exclude_message_id` (the request itself) is never returned."""
        needle = query.strip().casefold()
        if not needle or limit <= 0:
            return []
        found = [
            m
            for m in reversed(self._load(group_id))
            if needle in m.text.casefold()
            and m.message_id != exclude_message_id
            and (m.from_bot or (requester_user_id is not None and m.user_id == requester_user_id))
        ]
        return found[:limit]

    def remove(self, group_id: str, message_ids: set[str]) -> list[GroupMessage]:
        """Delete the messages with these ids from the record and return them, oldest first."""

        def is_listed(row: dict[str, Any]) -> bool:
            return str(row.get("message_id", "")) in message_ids

        return self._remove_where(group_id, is_listed)

    def remove_older_than(
        self, group_id: str, cutoff: datetime, *, keep_since: datetime | None
    ) -> list[GroupMessage]:
        """Delete the messages from before `cutoff`, except those from `keep_since` on
        (the running conversation's). A message whose time cannot be read is kept.
        Return what was deleted."""

        def is_expired(row: dict[str, Any]) -> bool:
            moment = _moment_of(row.get("time"))
            if row.get("imported") is True or moment is None or moment >= cutoff:
                return False
            return keep_since is None or moment < keep_since

        return self._remove_where(group_id, is_expired)

    def _remove_where(
        self, group_id: str, matches: Callable[[dict[str, Any]], bool]
    ) -> list[GroupMessage]:
        path = self._path(group_id)
        rows = read_json_lines(path)
        verdicts = [matches(row) for row in rows]
        if not any(verdicts):
            return []
        kept = [row for row, is_match in zip(rows, verdicts, strict=True) if not is_match]
        replace_json_lines(path, kept)
        removed = [row for row, is_match in zip(rows, verdicts, strict=True) if is_match]
        messages = [m for row in removed if (m := _message_of(row)) is not None]
        self._delete_images(group_id, messages)
        return messages

    def _delete_images(self, group_id: str, messages: list[GroupMessage]) -> None:
        images = self._path(group_id).parent / IMAGES_FOLDER_NAME
        for message in messages:
            if message.image_file:
                (images / Path(message.image_file).name).unlink(missing_ok=True)

    def _path(self, group_id: str) -> Path:
        if not GROUP_ID_PATTERN.match(group_id):
            raise ValueError("a group id holds only letters and digits")
        return self.state_dir / "groups" / group_id / "messages.jsonl"

    def _load(self, group_id: str) -> list[GroupMessage]:
        rows = read_json_lines(self._path(group_id))
        return [m for row in rows if (m := _message_of(row)) is not None]


def _message_of(row: dict[str, Any]) -> GroupMessage | None:
    text = row.get("text")
    if not isinstance(text, str):
        return None
    return GroupMessage(
        time=str(row.get("time", "")),
        message_id=str(row.get("message_id", "")),
        user_id=row.get("user_id"),
        display_name=row.get("display_name"),
        text=text,
        from_bot=row.get("from_bot") is True,
        image_file=row["image_file"] if isinstance(row.get("image_file"), str) else None,
        imported=row.get("imported") is True,
    )


def _sort_key(message: GroupMessage) -> float:
    moment = _moment_of(message.time)
    return moment.timestamp() if moment is not None else float("inf")


def _row_of(message: GroupMessage) -> dict[str, Any]:
    row = asdict(message)
    if message.image_file is None:
        del row["image_file"]
    if not message.imported:
        del row["imported"]
    return row


def _same_message_key(row: dict[str, Any]) -> tuple[str, str | None, str]:
    """What makes two rows the same message: the minute, the name and the text (an imported
    history has no seconds and no user ids)."""
    moment = _moment_of(row.get("time"))
    minute = moment.astimezone().strftime("%Y-%m-%d %H:%M") if moment is not None else ""
    return minute, row.get("display_name"), str(row.get("text", ""))


def _merged(rows: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return `rows` with `new` (oldest first) put in before the first row that is later than
    each of them. The order of `rows` is not changed; a row whose time cannot be read counts as
    the one before it."""
    merged: list[dict[str, Any]] = []
    index = 0
    last: datetime | None = None
    for row in rows:
        last = _moment_of(row.get("time")) or last
        while index < len(new) and last is not None and _is_before(new[index], last):
            merged.append(new[index])
            index += 1
        merged.append(row)
    merged.extend(new[index:])
    return merged


def _is_before(row: dict[str, Any], moment: datetime) -> bool:
    found = _moment_of(row.get("time"))
    return found is not None and found < moment


def _moment_of(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.astimezone() if moment.tzinfo is None else moment
