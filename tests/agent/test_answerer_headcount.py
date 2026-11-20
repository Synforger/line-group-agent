"""The answerer's envelope tells the model how many members the group has and which of them
the records know by name."""

from pathlib import Path

import pytest

from line_group_agent.agent.group_headcount import GroupHeadcount
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


class Counter:
    def __init__(self, count: int | None) -> None:
        self.count = count

    async def get_member_count(self, group_id: str) -> int | None:
        return self.count


def message(number: int, user_id: str, name: str, text: str) -> GroupMessage:
    return GroupMessage("2026-11-18T12:00:00+09:00", str(number), user_id, name, text)


def build(tmp_path: Path, count: int | None | str) -> World:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>")])
    if count != "unset":
        assert not isinstance(count, str)
        world.answerer.headcount = GroupHeadcount(Counter(count))
    world.group_log.add(GROUP, message(1, "U1", "Aki", "hi"))
    world.group_log.add(GROUP, message(2, "U2", "Ben", "hello"))
    return world


def first_turn(world: World) -> str:
    content = world.client.messages.requests[0]["messages"][0]["content"]
    assert isinstance(content, str)
    return content


async def test_the_turn_gives_the_group_size_and_the_names_the_records_know(
    tmp_path: Path,
) -> None:
    world = build(tmp_path, 4)
    await world.answerer.answer(GROUP, message(3, "U1", "Aki", "@bot split the bill"))
    assert 'This group has 4 members. Names the records know: "Aki", "Ben".' in first_turn(world)


async def test_the_line_is_left_out_when_line_gives_no_count(tmp_path: Path) -> None:
    world = build(tmp_path, None)
    await world.answerer.answer(GROUP, message(3, "U1", "Aki", "@bot split the bill"))
    assert "This group has" not in first_turn(world)


async def test_the_line_is_left_out_without_a_headcount(tmp_path: Path) -> None:
    world = build(tmp_path, "unset")
    await world.answerer.answer(GROUP, message(3, "U1", "Aki", "@bot split the bill"))
    assert "This group has" not in first_turn(world)
