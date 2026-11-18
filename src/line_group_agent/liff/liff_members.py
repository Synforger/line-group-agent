"""Who is in a group and what a member is called, as the voting page needs to know.

Asks LINE's group member profile and remembers the answers for a few minutes, so opening
the page again does not ask again. Called by the LIFF poll service.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol

from line_group_agent.liff.expiring_memory import ExpiringMemory

MEMORY_SECONDS = 300.0


class MemberDirectory(Protocol):
    """What LINE tells about a group's members (the LINE client)."""

    async def is_member(self, group_id: str, user_id: str) -> bool | None: ...

    async def get_member_name(self, group_id: str, user_id: str) -> str | None: ...


class LiffMembers:
    """Answers membership and display names from LINE, with a short memory."""

    def __init__(
        self, directory: MemberDirectory, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.directory = directory
        self._members: ExpiringMemory[tuple[str, str], bool] = ExpiringMemory(
            MEMORY_SECONDS, clock=clock
        )
        self._names: ExpiringMemory[tuple[str, str], str] = ExpiringMemory(
            MEMORY_SECONDS, clock=clock
        )

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        """Return whether the member is in the group, or None when LINE gave no clear answer
        (that is not remembered)."""
        key = (group_id, user_id)
        remembered = self._members.get(key)
        if remembered is not None:
            return remembered
        answer = await self.directory.is_member(group_id, user_id)
        if answer is not None:
            self._members.remember(key, answer)
        return answer

    async def name_of(self, group_id: str, user_id: str) -> str | None:
        """Return the member's display name, or None when LINE does not give it."""
        key = (group_id, user_id)
        remembered = self._names.get(key)
        if remembered is not None:
            return remembered
        name = await self.directory.get_member_name(group_id, user_id)
        if name is not None:
            self._names.remember(key, name)
        return name
