"""A poll of a group: a question, the options, and who picked each option.

Plain values, kept by the poll book in the group's `polls.json`; read by the poll
message, the poll text and the poll tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field

KIND_CHOICE = "choice"
KIND_DATE = "date"


@dataclass
class Voter:
    """A member who picked an option; `name` is the display name when LINE gave one."""

    user_id: str
    name: str | None


@dataclass
class PollOption:
    """One choice (or one candidate date) and the members who picked it."""

    label: str
    voters: list[Voter] = field(default_factory=list)


@dataclass
class Poll:
    """A poll. `id` is `p<number>`, counted up in the group; `kind` is `choice` or `date`.
    With `multiple` a member may pick several options; a closed poll takes no more votes.
    `link_id` is the unguessable id the voting page's link carries (empty on a poll made before
    the page existed, which cannot be opened there)."""

    id: str
    kind: str
    question: str
    options: list[PollOption]
    multiple: bool
    is_closed: bool
    created_at: str
    link_id: str = ""
