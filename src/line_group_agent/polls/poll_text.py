"""The words about a poll: the line that stands for it in the group's record, and the
result the model is given when it asks for the count.

Pure text building; called by the poll tools.
"""

from __future__ import annotations

from line_group_agent.polls.poll import KIND_DATE, Poll

POLL_RECORD_LABEL = "[投票]"
DATE_POLL_RECORD_LABEL = "[日程]"
ENTRY_SEPARATOR = " / "
UNKNOWN_VOTER = "someone"


def poll_record_line(poll: Poll) -> str:
    """Return `[投票] p1 question 1. a / 2. b` (`[日程]` for a date poll), so a later mention
    can still tell what was asked and which poll it was."""
    label = DATE_POLL_RECORD_LABEL if poll.kind == KIND_DATE else POLL_RECORD_LABEL
    entries = ENTRY_SEPARATOR.join(
        f"{number}. {option.label}" for number, option in enumerate(poll.options, start=1)
    )
    return f"{label} {poll.id} {poll.question} {entries}"


def format_poll_results(poll: Poll) -> str:
    """Return the count of a poll as plain text for the model: the state, then each option
    with how many picked it and who."""
    state = "closed" if poll.is_closed else "open"
    if poll.kind == KIND_DATE:
        mode = "date poll, members mark every date that suits them"
    else:
        mode = "pick several" if poll.multiple else "one vote each"
    lines = [f"Poll {poll.id} ({state}, {mode}): {poll.question}"]
    for number, option in enumerate(poll.options, start=1):
        names = ", ".join(voter.name or UNKNOWN_VOTER for voter in option.voters)
        suffix = f" ({names})" if names else ""
        lines.append(f"{number}. {option.label}: {len(option.voters)}{suffix}")
    people = {voter.user_id for option in poll.options for voter in option.voters}
    lines.append(f"{len(people)} member(s) have voted.")
    return "\n".join(lines)
