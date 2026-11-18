"""Photos the group sent since the bot's last turn are shown to the model with the turn."""

import base64
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.agent.prompt import photo_caption
from line_group_agent.media.image_shrinker import StoredImage
from line_group_agent.records.group_log import GroupMessage
from tests.fakes import text_answer
from tests.world import GROUP, World, build_world

pytestmark = pytest.mark.anyio


def add_photo(world: World, number: int, name: str = "Aki") -> GroupMessage:
    data = f"photo {number}".encode()
    file = world.images.save(GROUP, str(number), StoredImage(data, "image/png"))
    message = GroupMessage(f"t{number}", str(number), "U1", name, "[写真]", image_file=file)
    world.group_log.add(GROUP, message)
    return message


def add_mention(world: World, number: int = 99) -> GroupMessage:
    message = GroupMessage("t99", str(number), "U1", "Aki", "@bot what is this?")
    world.group_log.add(GROUP, message)
    return message


def first_content(world: World, request: int = 0) -> Any:
    return world.client.messages.requests[request]["messages"][-1]["content"]


async def test_a_photo_sent_before_the_mention_comes_with_the_turn(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>")])
    photo = add_photo(world, 1)
    await world.answerer.answer(GROUP, add_mention(world))
    envelope, caption, image = first_content(world)
    assert envelope["type"] == "text" and "[写真]" in envelope["text"]
    assert caption == {"type": "text", "text": photo_caption(photo)}
    assert image == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": base64.b64encode(b"photo 1").decode(),
        },
    }


async def test_without_a_photo_the_turn_stays_one_text(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>")])
    await world.answerer.answer(GROUP, add_mention(world))
    assert isinstance(first_content(world), str)


async def test_only_the_newest_photos_up_to_the_limit_are_shown(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>")], max_images_per_turn=2)
    for number in (1, 2, 3):
        add_photo(world, number)
    await world.answerer.answer(GROUP, add_mention(world))
    images = [b for b in first_content(world) if b["type"] == "image"]
    assert [base64.b64decode(b["source"]["data"]) for b in images] == [b"photo 2", b"photo 3"]


async def test_a_photo_already_shown_in_an_earlier_turn_is_not_shown_again(
    tmp_path: Path,
) -> None:
    world = build_world(
        tmp_path,
        [text_answer("<reply>a</reply>"), text_answer("<reply>b</reply>", message_id="m2")],
    )
    add_photo(world, 1)
    await world.answerer.answer(GROUP, add_mention(world, 90))
    world.group_log.add(GROUP, GroupMessage("t95", "bot-1", None, None, "a", from_bot=True))
    add_photo(world, 2)
    await world.answerer.answer(GROUP, add_mention(world, 91))
    second = first_content(world, 1)
    assert [b for b in second if b["type"] == "image"][0]["source"]["data"] == base64.b64encode(
        b"photo 2"
    ).decode()
    assert len([b for b in second if b["type"] == "image"]) == 1


async def test_a_photo_is_part_of_the_conversation_record_and_a_deleted_one_is_blanked(
    tmp_path: Path,
) -> None:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>")])
    photo = add_photo(world, 1)
    await world.answerer.answer(GROUP, add_mention(world))
    conversation = world.conversations.get(GROUP)
    assert conversation.messages[0]["content"][2]["type"] == "image"
    assert world.deleter.delete(GROUP, {photo.message_id}) == 1
    content = conversation.messages[0]["content"]
    assert [b["type"] for b in content] == ["text", "text"]
    assert content[1]["text"] == "[deleted]"
    assert "photo 1" not in (tmp_path / "state" / "conversations" / "g-callowed.jsonl").read_text()
    assert not (tmp_path / "state" / "groups" / GROUP / "images" / "1.png").exists()


async def test_the_turn_that_opens_a_generation_carries_photos_too(tmp_path: Path) -> None:
    world = build_world(tmp_path, [text_answer("<reply>ok</reply>")])
    conversation = world.conversations.get(GROUP)
    conversation.set_pending_summary("Notes so far", world.clock())
    add_photo(world, 1)
    await world.answerer.answer(GROUP, add_mention(world))
    content = first_content(world)
    assert content[0]["text"].startswith("Summary of the conversation so far\nNotes so far")
    assert content[2]["type"] == "image"
