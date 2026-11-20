import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from line_group_agent.agent.client_tool import ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import MAX_EXTRA_MESSAGES, TurnOutput
from line_group_agent.itinerary.itinerary import Itinerary
from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.itinerary.itinerary_images import ItineraryImages, ItineraryImageSet
from line_group_agent.itinerary.itinerary_tools import itinerary_tools
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.records.group_log import GroupMessage

pytestmark = pytest.mark.anyio
GROUP = "Cgroup"
LIFF_ID = "1234567890-AbCdEfGh"
MENTION = GroupMessage("t", "1", "U1", "Aki", "@bot plan as an image")
NOW = datetime(2026, 11, 23, 8, 0, tzinfo=timezone(timedelta(hours=9)))
URLS = ["https://bot.example/liff/media/a.png", "https://bot.example/liff/media/b.png"]


class FakeImages(ItineraryImages):
    def __init__(self, result: ItineraryImageSet | None) -> None:
        self.result = result
        self.calls = 0

    async def create(self, group_id: str, itinerary: Itinerary) -> ItineraryImageSet | None:
        self.calls += 1
        return self.result


class Setup:
    def __init__(
        self, tmp_path: Path, images: ItineraryImages | None, *, has_item: bool = True
    ) -> None:
        self.book = ItineraryBook(tmp_path, lambda: NOW)
        if has_item:
            self.book.add_item(GROUP, day=1, title="Kiyomizu", start="09:00")
        else:
            self.book.change_trip(GROUP, {"title": "Trip"})
        tools = itinerary_tools(self.book, liff_id=LIFF_ID, clock=lambda: NOW, images=images)
        self.get = next(tool for tool in tools if tool.name == "get_itinerary")
        self.output = TurnOutput()

    async def run(self, tool_input: object) -> ToolOutcome:
        outcome = self.get.run(tool_input, ToolTurn(GROUP, MENTION, self.output))
        assert inspect.isawaitable(outcome)
        return await outcome

    def types(self) -> list[str]:
        return [extra.message["type"] for extra in self.output.extras]


async def test_show_image_adds_an_image_message_for_each_image(tmp_path: Path) -> None:
    setup = Setup(tmp_path, FakeImages(ItineraryImageSet(URLS, 0)))
    outcome = await setup.run({"show_image": True})
    assert "2 image(s)" in outcome.content and not outcome.is_error
    assert setup.types() == ["image", "image"]
    extra: OutgoingExtra = setup.output.extras[0]
    assert extra.message == {
        "type": "image",
        "originalContentUrl": URLS[0],
        "previewImageUrl": URLS[0],
    }
    assert extra.record_line.startswith("[予定表の画像]")


async def test_show_image_and_show_card_send_the_images_first_then_the_card(tmp_path: Path) -> None:
    setup = Setup(tmp_path, FakeImages(ItineraryImageSet(URLS[:1], 0)))
    await setup.run({"show_image": True, "show_card": True})
    assert setup.types() == ["image", "flex"]


async def test_days_that_did_not_fit_are_told_to_the_model(tmp_path: Path) -> None:
    setup = Setup(tmp_path, FakeImages(ItineraryImageSet(URLS, 3)))
    assert "Not every day fits" in (await setup.run({"show_image": True})).content


async def test_without_show_image_nothing_is_drawn(tmp_path: Path) -> None:
    images = FakeImages(ItineraryImageSet(URLS, 0))
    setup = Setup(tmp_path, images)
    await setup.run({})
    await setup.run({"show_image": "yes"})
    assert images.calls == 0 and setup.output.extras == []


async def test_when_the_image_cannot_be_drawn_the_card_is_sent_instead(tmp_path: Path) -> None:
    setup = Setup(tmp_path, FakeImages(None))
    outcome = await setup.run({"show_image": True})
    assert "could not be drawn" in outcome.content and not outcome.is_error
    assert setup.types() == ["flex"]


async def test_without_images_set_up_the_card_is_sent_instead(tmp_path: Path) -> None:
    setup = Setup(tmp_path, None)
    outcome = await setup.run({"show_image": True})
    assert "images are not set up" in outcome.content
    assert setup.types() == ["flex"]


async def test_images_that_do_not_all_fit_are_cut_to_the_room_left(tmp_path: Path) -> None:
    setup = Setup(tmp_path, FakeImages(ItineraryImageSet(URLS * 2, 0)))
    for _ in range(MAX_EXTRA_MESSAGES - 1):
        setup.output.add(OutgoingExtra({"type": "text"}, "x"))
    outcome = await setup.run({"show_image": True})
    assert len(setup.output.extras) == MAX_EXTRA_MESSAGES
    assert "1 image(s)" in outcome.content and "Not every day fits" in outcome.content


async def test_a_reply_with_no_room_draws_nothing(tmp_path: Path) -> None:
    images = FakeImages(ItineraryImageSet(URLS, 0))
    setup = Setup(tmp_path, images)
    for _ in range(MAX_EXTRA_MESSAGES):
        setup.output.add(OutgoingExtra({"type": "text"}, "x"))
    assert "No image was sent" in (await setup.run({"show_image": True})).content
    assert images.calls == 0


async def test_an_empty_itinerary_draws_nothing(tmp_path: Path) -> None:
    images = FakeImages(ItineraryImageSet(URLS, 0))
    setup = Setup(tmp_path, images, has_item=False)
    assert "nothing on the itinerary" in (await setup.run({"show_image": True})).content
    assert images.calls == 0 and setup.output.extras == []
