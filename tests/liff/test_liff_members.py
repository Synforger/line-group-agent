import pytest

from line_group_agent.liff.liff_members import MEMORY_SECONDS, LiffMembers

pytestmark = pytest.mark.anyio


class CountingDirectory:
    def __init__(self) -> None:
        self.members: dict[str, bool | None] = {"U1": True, "U2": False}
        self.names: dict[str, str] = {"U1": "Aki"}
        self.member_lookups = 0
        self.name_lookups = 0

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        self.member_lookups += 1
        return self.members.get(user_id)

    async def get_member_name(self, group_id: str, user_id: str) -> str | None:
        self.name_lookups += 1
        return self.names.get(user_id)


def members_over(directory: CountingDirectory, now: list[float]) -> LiffMembers:
    return LiffMembers(directory, clock=lambda: now[0])


async def test_membership_is_asked_again_only_after_five_minutes() -> None:
    directory, now = CountingDirectory(), [0.0]
    members = members_over(directory, now)
    assert [await members.is_member("G", "U1"), await members.is_member("G", "U1")] == [True] * 2
    assert directory.member_lookups == 1
    now[0] = MEMORY_SECONDS
    await members.is_member("G", "U1")
    assert directory.member_lookups == 2


async def test_a_member_who_is_out_is_remembered_too() -> None:
    directory = CountingDirectory()
    members = members_over(directory, [0.0])
    assert [await members.is_member("G", "U2"), await members.is_member("G", "U2")] == [False] * 2
    assert directory.member_lookups == 1


async def test_an_unclear_answer_is_given_but_not_remembered() -> None:
    directory = CountingDirectory()
    members = members_over(directory, [0.0])
    assert await members.is_member("G", "U3") is None
    directory.members["U3"] = True
    assert await members.is_member("G", "U3") is True


async def test_the_same_member_in_another_group_is_asked_separately() -> None:
    directory = CountingDirectory()
    members = members_over(directory, [0.0])
    await members.is_member("G1", "U1")
    await members.is_member("G2", "U1")
    assert directory.member_lookups == 2


async def test_a_name_is_remembered_and_a_missing_one_is_asked_again() -> None:
    directory = CountingDirectory()
    members = members_over(directory, [0.0])
    assert [await members.name_of("G", "U1"), await members.name_of("G", "U1")] == ["Aki"] * 2
    assert directory.name_lookups == 1
    assert await members.name_of("G", "U9") is None
    assert await members.name_of("G", "U9") is None
    assert directory.name_lookups == 3
