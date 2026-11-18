"""The conversation record that a chat client shows as a read-only tab.

Written by the answerer at `<state_dir>/conversations/<tab_name>.jsonl`. Each line is
`{type, uuid, timestamp, message}`: a user row holds what was sent to the model, an
assistant row holds the API's answer as it came (with its `id`). No `parentUuid` is
written, the file is append only, and each row is one write.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from line_group_agent.records._internal.jsonl import append_json_line, end_with_newline


class ConversationLog:
    """Appends user and assistant rows to one conversation record."""

    def __init__(self, path: Path, *, clock: Callable[[], datetime] | None = None) -> None:
        self.path = path
        self._clock = clock or (lambda: datetime.now(UTC))

    def open(self) -> None:
        """Make the record ready to append: a cut last row gets its newline first."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        end_with_newline(self.path)

    def add_user(self, content: str | list[dict[str, Any]]) -> None:
        """Append what was sent as the user turn (text, or tool_result blocks)."""
        self._append("user", {"role": "user", "content": content})

    def add_assistant(self, message: dict[str, Any]) -> None:
        """Append the API's answer as it came; it must carry its `id`."""
        if not message.get("id"):
            raise ValueError("an assistant row needs the message id")
        self._append("assistant", message)

    def _append(self, row_type: str, message: dict[str, Any]) -> None:
        timestamp = self._clock().astimezone(UTC).isoformat(timespec="milliseconds")
        row = {
            "type": row_type,
            "uuid": str(uuid.uuid4()),
            "timestamp": timestamp.replace("+00:00", "Z"),
            "message": message,
        }
        append_json_line(self.path, row)
