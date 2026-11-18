"""The summaries that close a generation of a group's conversation, one file each.

Written when a conversation is rolled over and read at start to find the latest one, so
the conversation can tell whether it has used it yet and which generation it is in.
Summaries are never deleted by the agent; one is rewritten only to take out what a member
had deleted. Lives at
`<state_dir>/groups/<groupId>/journal/<YYYY-MM-DD>-gen<N>.md`, where N is the
generation the summary closes. The file holds the summary text only.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path

from line_group_agent._common.atomic_write import write_text_atomically
from line_group_agent.records.group_log import GROUP_ID_PATTERN

GENERATION_PATTERN = re.compile(r"-gen(\d+)\.md$")


class SummaryJournal:
    """Reads and writes the per-group summary files under one state folder."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    def write(self, group_id: str, generation: int, text: str, day: date) -> Path:
        """Write the summary that closes `generation` and return its path."""
        path = self._folder(group_id) / f"{day.isoformat()}-gen{generation}.md"
        write_text_atomically(path, text.strip() + "\n")
        return path

    def read(self, group_id: str, generation: int) -> tuple[str, datetime] | None:
        """Return the summary that closes `generation` and when it was written, or None.

        When several files exist for the generation, the latest one counts.
        """
        folder = self._folder(group_id)
        if not folder.is_dir():
            return None
        found = sorted(folder.glob(f"*-gen{generation}.md"))
        if not found:
            return None
        path = found[-1]
        try:
            text = path.read_text(encoding="utf-8").strip()
            written_at = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
        except OSError:
            return None
        return (text, written_at) if text else None

    def list_paths(self, group_id: str) -> list[Path]:
        """Return every summary file of the group, oldest generation first."""
        folder = self._folder(group_id)
        if not folder.is_dir():
            return []
        found = [(int(m.group(1)), path) for path in folder.glob("*-gen*.md")
                 if (m := GENERATION_PATTERN.search(path.name))]  # fmt: skip
        return [path for _, path in sorted(found)]

    def rewrite(self, path: Path, text: str) -> None:
        """Replace the text of a summary file, keeping its modification time (which tells when
        the summary was written)."""
        stamp = path.stat().st_mtime_ns
        write_text_atomically(path, text.strip() + "\n")
        os.utime(path, ns=(stamp, stamp))

    def latest_generation(self, group_id: str) -> int | None:
        """Return the highest generation a summary file closes, or None without any."""
        folder = self._folder(group_id)
        if not folder.is_dir():
            return None
        numbers = [
            int(found.group(1))
            for path in folder.glob("*-gen*.md")
            if (found := GENERATION_PATTERN.search(path.name))
        ]
        return max(numbers, default=None)

    def _folder(self, group_id: str) -> Path:
        if not GROUP_ID_PATTERN.match(group_id):
            raise ValueError("a group id holds only letters and digits")
        return self.state_dir / "groups" / group_id / "journal"
