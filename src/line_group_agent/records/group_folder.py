"""Where a group's files live: `<state_dir>/groups/<groupId>/`.

Called by the stores of the group tools (polls, itinerary, images) so each checks the
group id the same way before it builds a path.
"""

from __future__ import annotations

from pathlib import Path

from line_group_agent.records.group_log import GROUP_ID_PATTERN


def group_folder(state_dir: Path, group_id: str) -> Path:
    """Return the group's folder (not created), refusing an id that is not letters and digits."""
    if not GROUP_ID_PATTERN.match(group_id):
        raise ValueError("a group id holds only letters and digits")
    return state_dir / "groups" / group_id
