"""Write what a run produced: a scenario's `transcript.json` and `chat.html`, and the front
page `index.html` of all of them.

Writes files; called by the simulation. A photo a member sent is made small and put into the
chat page as a `data:` address so the page is one file.
"""

from __future__ import annotations

import base64
import io
import json
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from line_group_agent.simulator.chat_page import render_chat_page
from line_group_agent.simulator.index_page import render_index_page
from line_group_agent.simulator.transcript import ScenarioTranscript

TRANSCRIPT_FILE = "transcript.json"
CHAT_FILE = "chat.html"
INDEX_FILE = "index.html"
PHOTO_EDGE_PIXELS = 640
PHOTO_QUALITY = 80


def write_scenario_report(scenario_dir: Path, transcript: ScenarioTranscript) -> Path:
    """Write the transcript and the chat page into `scenario_dir` and return the chat page."""
    scenario_dir.mkdir(parents=True, exist_ok=True)
    (scenario_dir / TRANSCRIPT_FILE).write_text(
        json.dumps(asdict(transcript), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    chat_file = scenario_dir / CHAT_FILE
    chat_file.write_text(
        render_chat_page(transcript, _photo_addresses(transcript)), encoding="utf-8"
    )
    return chat_file


def write_index(out_dir: Path, transcripts: Sequence[ScenarioTranscript]) -> Path:
    """Write the front page of all the scenarios into `out_dir` and return it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    index_file = out_dir / INDEX_FILE
    index_file.write_text(render_index_page(transcripts), encoding="utf-8")
    return index_file


def _photo_addresses(transcript: ScenarioTranscript) -> dict[str, str]:
    """Map each photo file a member sent to a small `data:` address of it."""
    addresses: dict[str, str] = {}
    for step in transcript.steps:
        file = (step.shown or {}).get("file")
        if step.kind == "image" and isinstance(file, str) and file not in addresses:
            address = _address_of(Path(file))
            if address is not None:
                addresses[file] = address
    return addresses


def _address_of(file: Path) -> str | None:
    try:
        with Image.open(file) as image:
            small = image.convert("RGB")
            small.thumbnail((PHOTO_EDGE_PIXELS, PHOTO_EDGE_PIXELS))
            buffer = io.BytesIO()
            small.save(buffer, format="JPEG", quality=PHOTO_QUALITY)
    except (OSError, UnidentifiedImageError):
        return None
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
