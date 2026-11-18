"""The polls of every group: made by the poll tools, voted on by the postback handler and by
the voting page.

Lives at `<state_dir>/groups/<groupId>/polls.json`, one file per group, replaced whole at
each change. Votes are counted here, in code, so a vote costs nothing and the model is
only asked to read the result. The newest polls are kept (`MAX_POLLS_KEPT`).
"""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from line_group_agent.polls.poll import KIND_CHOICE, Poll, PollOption, Voter
from line_group_agent.records.group_folder import group_folder
from line_group_agent.records.group_log import GROUP_ID_PATTERN
from line_group_agent.records.json_document import read_json_document, write_json_document

POLLS_FILE_NAME = "polls.json"
POLL_ID_PREFIX = "p"
MAX_POLLS_KEPT = 50
# 16 random bytes in base64url: 128 bits, 22 characters.
LINK_ID_BYTES = 16
LINK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


class VoteResult(StrEnum):
    """What a vote did: it was counted, it took the member's earlier vote back, it changed
    nothing (a one-pick poll pressed again on the option already picked), or it was ignored
    (an unknown or closed poll, or an option that does not exist)."""

    COUNTED = "counted"
    WITHDRAWN = "withdrawn"
    UNCHANGED = "unchanged"
    IGNORED = "ignored"


@dataclass(frozen=True)
class PollLocation:
    """A poll and the group it belongs to, found by the id of its link."""

    group_id: str
    poll: Poll


class PollBook:
    """Reads and changes the polls under one state folder."""

    def __init__(self, state_dir: Path, clock: Callable[[], datetime]) -> None:
        self.state_dir = state_dir
        self._clock = clock

    def create(
        self,
        group_id: str,
        question: str,
        labels: Sequence[str],
        *,
        kind: str = KIND_CHOICE,
        multiple: bool = False,
    ) -> Poll:
        """Make a poll with a new id and keep it."""
        document = self._read(group_id)
        number = int(document.get("last_number", 0)) + 1
        poll = Poll(
            id=f"{POLL_ID_PREFIX}{number}",
            kind=kind,
            question=question,
            options=[PollOption(label) for label in labels],
            multiple=multiple,
            is_closed=False,
            created_at=self._clock().isoformat(timespec="seconds"),
            link_id=secrets.token_urlsafe(LINK_ID_BYTES),
        )
        polls = [*_polls_of(document), poll][-MAX_POLLS_KEPT:]
        self._write(group_id, number, polls)
        return poll

    def get(self, group_id: str, poll_id: str | None = None) -> Poll | None:
        """Return the poll with this id, or (without an id) the newest open poll, else the
        newest one. None when there is no such poll."""
        polls = _polls_of(self._read(group_id))
        if poll_id is not None:
            return _find(polls, poll_id)
        open_polls = [poll for poll in polls if not poll.is_closed]
        found = open_polls or polls
        return found[-1] if found else None

    def find_by_link_id(self, link_id: str) -> PollLocation | None:
        """Return the poll whose voting-page link carries this id, with its group, or None
        when no group has one (an id of the wrong shape is not looked up at all)."""
        if not LINK_ID_PATTERN.match(link_id):
            return None
        groups_folder = self.state_dir / "groups"
        try:
            folders = sorted(groups_folder.iterdir())
        except OSError:
            return None
        for folder in folders:
            if not GROUP_ID_PATTERN.match(folder.name):
                continue
            for poll in _polls_of(self._read(folder.name)):
                if poll.link_id and secrets.compare_digest(poll.link_id.encode(), link_id.encode()):
                    return PollLocation(folder.name, poll)
        return None

    def vote(
        self, group_id: str, poll_id: str, option_index: int, user_id: str, name: str | None
    ) -> VoteResult:
        """Count a member's vote. In a poll that allows several picks each option is a switch:
        a press picks it, a second press takes it back. In a poll that allows one pick, a press
        on another option moves the vote and a second press on the option already picked
        changes nothing (taking the vote back is `withdraw`)."""
        document = self._read(group_id)
        polls = _polls_of(document)
        poll = _find(polls, poll_id)
        if poll is None or poll.is_closed or not 0 <= option_index < len(poll.options):
            return VoteResult.IGNORED
        option = poll.options[option_index]
        if any(voter.user_id == user_id for voter in option.voters):
            if not poll.multiple:
                return VoteResult.UNCHANGED
            option.voters = [voter for voter in option.voters if voter.user_id != user_id]
            result = VoteResult.WITHDRAWN
        else:
            if not poll.multiple:
                for other in poll.options:
                    other.voters = [voter for voter in other.voters if voter.user_id != user_id]
            option.voters.append(Voter(user_id, name))
            result = VoteResult.COUNTED
        self._write(group_id, int(document.get("last_number", 0)), polls)
        return result

    def withdraw(self, group_id: str, poll_id: str, user_id: str) -> VoteResult:
        """Take back every vote this member has in the poll: WITHDRAWN when there was one,
        else IGNORED (an unknown or closed poll, or no vote of the member's)."""
        document = self._read(group_id)
        polls = _polls_of(document)
        poll = _find(polls, poll_id)
        if poll is None or poll.is_closed:
            return VoteResult.IGNORED
        if not any(voter.user_id == user_id for option in poll.options for voter in option.voters):
            return VoteResult.IGNORED
        for option in poll.options:
            option.voters = [voter for voter in option.voters if voter.user_id != user_id]
        self._write(group_id, int(document.get("last_number", 0)), polls)
        return VoteResult.WITHDRAWN

    def close(self, group_id: str, poll_id: str | None = None) -> Poll | None:
        """Close the poll (the newest open one without an id) and return it, or None when
        there is no open poll to close."""
        document = self._read(group_id)
        polls = _polls_of(document)
        if poll_id is None:
            open_polls = [poll for poll in polls if not poll.is_closed]
            poll = open_polls[-1] if open_polls else None
        else:
            poll = _find(polls, poll_id)
        if poll is None or poll.is_closed:
            return None
        poll.is_closed = True
        self._write(group_id, int(document.get("last_number", 0)), polls)
        return poll

    def _read(self, group_id: str) -> dict[str, Any]:
        return read_json_document(self._path(group_id))

    def _write(self, group_id: str, last_number: int, polls: list[Poll]) -> None:
        document = {"last_number": last_number, "polls": [_row_of(poll) for poll in polls]}
        write_json_document(self._path(group_id), document)

    def _path(self, group_id: str) -> Path:
        return group_folder(self.state_dir, group_id) / POLLS_FILE_NAME


def _find(polls: list[Poll], poll_id: str) -> Poll | None:
    wanted = poll_id.strip().casefold()
    if wanted.isdigit():
        wanted = f"{POLL_ID_PREFIX}{wanted}"
    return next((poll for poll in polls if poll.id == wanted), None)


def _polls_of(document: dict[str, Any]) -> list[Poll]:
    rows = document.get("polls")
    if not isinstance(rows, list):
        return []
    return [poll for row in rows if (poll := _poll_of(row)) is not None]


def _poll_of(row: Any) -> Poll | None:
    if not isinstance(row, dict) or not isinstance(row.get("id"), str):
        return None
    options = row.get("options")
    if not isinstance(options, list):
        return None
    return Poll(
        id=row["id"],
        kind=str(row.get("kind", KIND_CHOICE)),
        question=str(row.get("question", "")),
        options=[_option_of(option) for option in options if isinstance(option, dict)],
        multiple=row.get("multiple") is True,
        is_closed=row.get("is_closed") is True,
        created_at=str(row.get("created_at", "")),
        link_id=str(row.get("link_id", "")),
    )


def _option_of(row: dict[str, Any]) -> PollOption:
    voters = row.get("voters")
    return PollOption(
        label=str(row.get("label", "")),
        voters=[
            Voter(voter["user_id"], voter.get("name"))
            for voter in voters or []
            if isinstance(voter, dict) and isinstance(voter.get("user_id"), str)
        ],
    )


def _row_of(poll: Poll) -> dict[str, Any]:
    return {
        "id": poll.id,
        "kind": poll.kind,
        "question": poll.question,
        "multiple": poll.multiple,
        "is_closed": poll.is_closed,
        "created_at": poll.created_at,
        "link_id": poll.link_id,
        "options": [
            {
                "label": option.label,
                "voters": [{"user_id": v.user_id, "name": v.name} for v in option.voters],
            }
            for option in poll.options
        ],
    }
