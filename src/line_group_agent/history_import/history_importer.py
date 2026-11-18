"""Put the messages of an old chat history into a group's record.

The messages are marked `imported`, so age does not delete them (they are old by nature) and
they are told from live ones. A message the record already holds (the same minute, name and
text) is not added, so running the import again adds nothing. They carry no user id, and a
message id made from what the message says, so the same history always gets the same ids.

Called by the import command.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass

from line_group_agent.history_import.history_parser import HistoryMessage, parse_history
from line_group_agent.records.group_log import GroupLog, GroupMessage

IMPORT_ID_PREFIX = "import-"
ID_DIGEST_CHARS = 16


@dataclass(frozen=True)
class ImportResult:
    """What an import did: messages added, messages the record already held, notice lines
    skipped on purpose, and lines that were not understood."""

    added_count: int
    existing_count: int
    notice_count: int
    unrecognized_count: int


class HistoryImporter:
    """Imports a chat history file's text into a group's record."""

    def __init__(self, group_log: GroupLog) -> None:
        self.group_log = group_log

    def import_text(self, group_id: str, text: str) -> ImportResult:
        """Parse `text` and add what the record does not hold yet."""
        parsed = parse_history(text)
        messages = _group_messages_of(parsed.messages)
        added = self.group_log.add_imported(group_id, messages)
        return ImportResult(
            added_count=added,
            existing_count=len(messages) - added,
            notice_count=parsed.notice_count,
            unrecognized_count=parsed.unrecognized_count,
        )


def _group_messages_of(history: list[HistoryMessage]) -> list[GroupMessage]:
    seen: Counter[str] = Counter()
    messages: list[GroupMessage] = []
    for entry in history:
        time = entry.moment.astimezone().isoformat(timespec="seconds")
        key = f"{time}|{entry.name}|{entry.text}"
        seen[key] += 1
        digest = hashlib.sha256(f"{key}|{seen[key]}".encode()).hexdigest()[:ID_DIGEST_CHARS]
        messages.append(
            GroupMessage(
                time=time,
                message_id=f"{IMPORT_ID_PREFIX}{digest}",
                user_id=None,
                display_name=entry.name,
                text=entry.text,
                imported=True,
            )
        )
    return messages
