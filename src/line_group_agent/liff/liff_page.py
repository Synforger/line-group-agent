"""The LIFF pages: each one HTML file (its script and styles inside) that LINE opens in the app,
the voting page and the itinerary page.

A file holds no group content; the page asks the API for it once opened. Only the LIFF id is
put in, at start. Called by the service builder, which hands the text to the web app.
"""

from __future__ import annotations

import json
from pathlib import Path

PAGE_FILE = Path(__file__).with_name("liff_page.html")
ITINERARY_PAGE_FILE = Path(__file__).with_name("itinerary_page.html")
LIFF_ID_PLACEHOLDER = '"__LIFF_ID__"'


def load_liff_page(liff_id: str) -> str:
    """Return the voting page with `liff_id` written into its script as a quoted string."""
    return _with_liff_id(PAGE_FILE, liff_id)


def load_itinerary_page(liff_id: str) -> str:
    """Return the itinerary page with `liff_id` written into its script as a quoted string."""
    return _with_liff_id(ITINERARY_PAGE_FILE, liff_id)


def _with_liff_id(file: Path, liff_id: str) -> str:
    literal = json.dumps(liff_id).replace("<", "\\u003c")
    return file.read_text(encoding="utf-8").replace(LIFF_ID_PLACEHOLDER, literal)
