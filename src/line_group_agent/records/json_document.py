"""One small JSON object kept in one file, replaced whole each time it changes.

Called by the poll book and the itinerary book. A file that is missing, cut or not an
object reads as an empty document, so a damaged file never stops an answer.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from line_group_agent._common.atomic_write import write_text_atomically


def read_json_document(path: Path) -> dict[str, Any]:
    """Return the JSON object in `path`, or an empty one when there is none to read."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return document if isinstance(document, dict) else {}


def write_json_document(path: Path, document: dict[str, Any]) -> None:
    """Replace the file with `document` (a temporary file, then a rename)."""
    write_text_atomically(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
