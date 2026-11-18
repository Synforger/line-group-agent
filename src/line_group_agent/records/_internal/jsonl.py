"""Append-only JSON Lines files: one object per line, each line written in one call.

Used by the group record and the conversation record.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def append_json_line(path: Path, row: dict[str, Any]) -> None:
    """Append `row` as one line, in a single write so a reader never sees half a row."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(descriptor, line)
    finally:
        os.close(descriptor)


def end_with_newline(path: Path) -> None:
    """Write one newline if the file does not end in one, so a row cut by a crash
    does not run into the next row."""
    if not path.exists() or path.stat().st_size == 0:
        return
    with path.open("rb") as file:
        file.seek(-1, os.SEEK_END)
        last = file.read(1)
    if last != b"\n":
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(descriptor, b"\n")
        finally:
            os.close(descriptor)


def read_json_lines(path: Path) -> list[dict[str, Any]]:
    """Read every whole row; a line that is not a JSON object is skipped."""
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.endswith("\n"):
                break
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows
