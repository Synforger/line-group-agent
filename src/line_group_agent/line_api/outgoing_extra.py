"""A LINE message the tools add after the reply text and the cards (a poll card, a location),
with the line that stands for it in the group's record.

Built by the group tools; sent by the LINE client and written to the record by the event
dispatcher once LINE has taken it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class OutgoingExtra:
    """`message` is the LINE message object; `record_line` is its one line in the record."""

    message: dict[str, Any]
    record_line: str
