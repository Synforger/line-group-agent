"""What the tools of one mention add to the reply besides its text and its cards: extra
messages (a poll card, a location) and quick reply buttons.

Made by the answerer for each mention, filled by the client tools, and turned into the
answer's extras at the end of the turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem

# LINE takes 5 messages per call: the reply text, the cards and up to three of these.
MAX_EXTRA_MESSAGES = 3
LOCATION_TYPE = "location"


@dataclass
class TurnOutput:
    """The extras and quick replies collected during one mention."""

    extras: list[OutgoingExtra] = field(default_factory=list)
    quick_replies: list[QuickReplyItem] = field(default_factory=list)

    def has_room(self) -> bool:
        """Whether one more extra message still fits in the reply."""
        return len(self.extras) < MAX_EXTRA_MESSAGES

    def has_location(self) -> bool:
        """Whether a location is already part of the reply (one per reply)."""
        return any(extra.message.get("type") == LOCATION_TYPE for extra in self.extras)

    def add(self, extra: OutgoingExtra) -> None:
        """Add an extra message; the caller checks `has_room` first."""
        self.extras.append(extra)
