"""The voting page: one HTML file (its script and styles inside) that LINE opens in the app.

The file holds no group content; the page asks the poll API for it once opened. Only the LIFF
id is put in, at start. Called by the service builder, which hands the text to the web app.
"""

from __future__ import annotations

import json
from pathlib import Path

PAGE_FILE = Path(__file__).with_name("liff_page.html")
LIFF_ID_PLACEHOLDER = '"__LIFF_ID__"'


def load_liff_page(liff_id: str) -> str:
    """Return the page with `liff_id` written into its script as a quoted string."""
    literal = json.dumps(liff_id).replace("<", "\\u003c")
    return PAGE_FILE.read_text(encoding="utf-8").replace(LIFF_ID_PLACEHOLDER, literal)
