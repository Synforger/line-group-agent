"""Quick reply buttons: the choices LINE shows under a message, each one sending a text
when it is tapped.

Pure shape-building, no I/O; called by the LINE client when a message carries them.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

MAX_QUICK_REPLY_COUNT = 13
LABEL_MAX_CHARS = 20
TEXT_MAX_CHARS = 300


@dataclass(frozen=True)
class QuickReplyItem:
    """One button: `label` is what it shows (up to 20 characters), `text` what a tap sends."""

    label: str
    text: str


def build_quick_reply(items: Sequence[QuickReplyItem]) -> dict[str, Any]:
    """Return the `quickReply` object for a message: one message-action button per item."""
    return {
        "items": [
            {
                "type": "action",
                "action": {"type": "message", "label": item.label, "text": item.text},
            }
            for item in items[:MAX_QUICK_REPLY_COUNT]
        ]
    }
