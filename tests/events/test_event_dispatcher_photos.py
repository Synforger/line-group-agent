"""A photo a member sends is kept and recorded as a line; nothing is answered."""

from pathlib import Path
from typing import Any

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.media.image_store import ImageStore
from line_group_agent.media.media_recorder import MediaRecorder
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import ALLOWED, ScriptedAnswerer
from tests.fakes import FakeLine
from tests.media.pictures import picture

pytestmark = pytest.mark.anyio


def image_event(message_id: str = "m1", provider: str = "line") -> dict[str, Any]:
    return {
        "type": "message",
        "replyToken": "reply-token-1",
        "timestamp": 1_763_434_800_000,
        "source": {"type": "group", "groupId": ALLOWED, "userId": "U1"},
        "message": {
            "type": "image",
            "id": message_id,
            "quoteToken": "q",
            "contentProvider": {"type": provider},
        },
    }


def setup(
    tmp_path: Path, *, with_media: bool = True, contents: dict[str, tuple[bytes, str]] | None = None
) -> tuple[EventDispatcher, FakeLine, GroupLog, ScriptedAnswerer]:
    line = FakeLine(names={"U1": "Aki"}, contents=contents)
    group_log = GroupLog(tmp_path)
    answerer = ScriptedAnswerer()
    media = MediaRecorder(line, ImageStore(tmp_path), 1000) if with_media else None
    dispatcher = EventDispatcher(frozenset({ALLOWED}), line, group_log, answerer, media=media)
    return dispatcher, line, group_log, answerer


async def test_a_photo_is_kept_and_recorded_as_a_line_with_its_file(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer = setup(
        tmp_path, contents={"m1": (picture(), "image/png")}
    )
    await dispatcher.handle(image_event())
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.text == "[写真]" and recorded.image_file == "m1.png"
    assert recorded.display_name == "Aki" and recorded.user_id == "U1"
    assert (tmp_path / "groups" / ALLOWED / "images" / "m1.png").exists()
    assert answerer.calls == [] and line.calls == []


async def test_a_photo_whose_content_cannot_be_read_is_still_recorded(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    await dispatcher.handle(image_event())
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.text == "[写真]" and recorded.image_file is None


async def test_a_photo_at_an_outside_address_is_recorded_without_asking_LINE_for_it(
    tmp_path: Path,
) -> None:
    dispatcher, line, group_log, _ = setup(tmp_path, contents={"m1": (picture(), "image/png")})
    await dispatcher.handle(image_event(provider="external"))
    assert group_log.list_recent(ALLOWED, 10)[0].image_file is None
    assert line.content_lookups == []


async def test_the_same_photo_delivered_again_is_kept_once(tmp_path: Path) -> None:
    dispatcher, line, group_log, _ = setup(tmp_path, contents={"m1": (picture(), "image/png")})
    await dispatcher.handle(image_event())
    await dispatcher.handle(image_event())
    assert len(group_log.list_recent(ALLOWED, 10)) == 1
    assert line.content_lookups == ["m1"]


async def test_without_a_recorder_photos_are_ignored_as_before(tmp_path: Path) -> None:
    dispatcher, line, group_log, _ = setup(tmp_path, with_media=False)
    await dispatcher.handle(image_event())
    assert group_log.list_recent(ALLOWED, 10) == [] and line.content_lookups == []


def location_event(**message: Any) -> dict[str, Any]:
    event = image_event()
    event["message"] = {
        "type": "location",
        "id": "m2",
        "title": "Gion Inn",
        "address": "Kyoto",
        "latitude": 35.0036,
        "longitude": 135.7756,
        **message,
    }
    return event


async def test_a_shared_location_is_recorded_as_a_line(tmp_path: Path) -> None:
    dispatcher, line, group_log, answerer = setup(tmp_path, with_media=False)
    await dispatcher.handle(location_event())
    [recorded] = group_log.list_recent(ALLOWED, 10)
    assert recorded.text == "[位置] Gion Inn Kyoto (35.0036, 135.7756)"
    assert recorded.display_name == "Aki" and recorded.image_file is None
    assert answerer.calls == [] and line.calls == []


async def test_a_location_without_coordinates_is_dropped(tmp_path: Path) -> None:
    dispatcher, _, group_log, _ = setup(tmp_path)
    await dispatcher.handle(location_event(latitude="35"))
    assert group_log.list_recent(ALLOWED, 10) == []
