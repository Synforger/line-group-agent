"""The members of a group that a reply may mention, read from the group's record.

Pure function over recorded messages; called by the answer sender.
"""

from __future__ import annotations

from collections.abc import Sequence

from line_group_agent.records.group_log import GroupMessage


def speakers_of(messages: Sequence[GroupMessage]) -> dict[str, str]:
    """Return the name of each member in the messages and their user id.

    A name that two members have is left out, so a mention never reaches the wrong one;
    the bot's own replies and messages without a user id or a name are not read.
    """
    owners: dict[str, set[str]] = {}
    for message in messages:
        name = (message.display_name or "").strip()
        if message.from_bot or not message.user_id or not name:
            continue
        owners.setdefault(name, set()).add(message.user_id)
    return {name: next(iter(ids)) for name, ids in owners.items() if len(ids) == 1}
