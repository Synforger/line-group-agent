"""What the itinerary page may do: open the group's itinerary, for a member who proves who they
are.

The member passes the gate (ID token and request count), the itinerary is found by the
unguessable id of its page's link, and the member must be in that itinerary's group; only then
is the plan given. A refusal is a `LiffRefusal`. The page only shows the plan; it is changed by
talking to the bot. Called by the LIFF router.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.liff.itinerary_view import itinerary_view_of
from line_group_agent.liff.liff_gate import LiffGate
from line_group_agent.liff.liff_members import LiffMembers
from line_group_agent.liff.liff_refusal import HTTP_FORBIDDEN, HTTP_UNAVAILABLE, LiffRefusal

logger = logging.getLogger(__name__)


class LiffItineraries:
    """Opens itineraries for the itinerary page."""

    def __init__(
        self,
        itineraries: ItineraryBook,
        gate: LiffGate,
        members: LiffMembers,
        *,
        is_group_allowed: Callable[[str], bool],
    ) -> None:
        self.itineraries = itineraries
        self.gate = gate
        self.members = members
        self.is_group_allowed = is_group_allowed

    async def show(self, id_token: str, link_id: str, source: str | None) -> dict[str, Any]:
        """Return the itinerary of this link as the page draws it. `source` is the address the
        request came from, or None when it is not known."""
        user_id = await self.gate.admit(id_token, source)
        location = self.itineraries.find_by_link_id(link_id)
        if location is None or not self.is_group_allowed(location.group_id):
            logger.info("liff: refused, no such itinerary")
            raise LiffRefusal(HTTP_FORBIDDEN)
        is_member = await self.members.is_member(location.group_id, user_id)
        if is_member is None:
            logger.warning("liff: refused, LINE did not say whether the member is in the group")
            raise LiffRefusal(HTTP_UNAVAILABLE)
        if not is_member:
            logger.info("liff: refused, not a member of the group")
            raise LiffRefusal(HTTP_FORBIDDEN)
        # Read it again: it may have changed while LINE was being asked.
        current = self.itineraries.get(location.group_id) or location.itinerary
        return itinerary_view_of(current)
