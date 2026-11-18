"""The shape of a poll as the voting page gets it: the question, each option's count and the
names of the members who picked it, and which options the viewer picked.

Pure shaping, no I/O; called by the LIFF poll service. The viewer is told by id only: a
member's id never leaves the server, only display names do.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from line_group_agent.polls.poll import Poll

UNNAMED_VOTER = "名前なし"


def unnamed_voter_ids(poll: Poll) -> list[str]:
    """Return the ids of the members whose vote has no display name kept, each once."""
    ids: dict[str, None] = {}
    for option in poll.options:
        for voter in option.voters:
            if not voter.name:
                ids[voter.user_id] = None
    return list(ids)


def poll_view_of(poll: Poll, viewer_id: str, found_names: Mapping[str, str]) -> dict[str, Any]:
    """Return the poll as JSON-ready values. `found_names` gives a name, by member id, to
    the voters whose vote kept none."""
    people = {voter.user_id for option in poll.options for voter in option.voters}
    return {
        "question": poll.question,
        "kind": poll.kind,
        "multiple": poll.multiple,
        "is_closed": poll.is_closed,
        "voter_count": len(people),
        "options": [
            {
                "label": option.label,
                "count": len(option.voters),
                "voters": [
                    voter.name or found_names.get(voter.user_id) or UNNAMED_VOTER
                    for voter in option.voters
                ],
                "mine": any(voter.user_id == viewer_id for voter in option.voters),
            }
            for option in poll.options
        ],
    }
