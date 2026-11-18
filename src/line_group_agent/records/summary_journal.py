"""The summaries that close a generation of a group's conversation, one file each.

Written when a conversation is rolled over and read at start to find a summary that
the next conversation has not used yet. Lives at
`<state_dir>/groups/<groupId>/journal/<YYYY-MM-DD>-gen<N>.md`, where N is the
generation the summary closes. The file holds the summary text only.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from line_group_agent._common.atomic_write import write_text_atomically
from line_group_agent.records.group_log import GROUP_ID_PATTERN


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

    def _folder(self, group_id: str) -> Path:
        if not GROUP_ID_PATTERN.match(group_id):
            raise ValueError("a group id holds only letters and digits")
        return self.state_dir / "groups" / group_id / "journal"
