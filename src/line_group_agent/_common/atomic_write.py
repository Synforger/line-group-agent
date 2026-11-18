"""Replace a whole file in one step: write a temporary file in the same folder, then
rename it over the old one, so a reader never sees half a file.

Called by the spend ledger, the tab list and the summary journal.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomically(path: Path, text: str) -> None:
    """Write `text` to `path` (creating its folder) by a temporary file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.stem}-", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
