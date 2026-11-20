"""Read the members a reply may mention from a group's record.

Called by the answer sender (a reply with `<mention>` marks) and by the reminder sender
(a reminder that calls members by name).
"""

from __future__ import annotations

from line_group_agent.events.group_speakers import speakers_of
from line_group_agent.records.group_log import GroupLog

# How far back in the group's record the names of the members who may be mentioned are read.
SPEAKER_LOOKUP_MESSAGES = 1000


def speakers_in(group_log: GroupLog, group_id: str) -> dict[str, str]:
    """Return each name the group's record holds for exactly one member, to that member's
    user id."""
    return speakers_of(group_log.list_recent(group_id, SPEAKER_LOOKUP_MESSAGES))
