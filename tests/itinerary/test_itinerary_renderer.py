"""The drawing side, with a real headless Chromium. Skipped where Playwright or its browser is
not installed (`uv run playwright install chromium`)."""

import io

import pytest
from PIL import Image

from line_group_agent._common.headless_browser import BrowserUnavailableError, HeadlessBrowser
from line_group_agent.itinerary.itinerary import Itinerary, ItineraryItem
from line_group_agent.itinerary.itinerary_renderer import (
    IMAGE_WIDTH_PX,
    ItineraryRenderer,
    RenderedItinerary,
)
from line_group_agent.liff.itinerary_view import itinerary_view_of

pytestmark = pytest.mark.anyio
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.fixture(autouse=True)
async def _browser_exists() -> None:
    try:
        async with HeadlessBrowser():
            return
    except BrowserUnavailableError as error:
        pytest.skip(str(error))


def itinerary_of(*items: ItineraryItem) -> Itinerary:
    return Itinerary("Kyoto trip", "2026-11-23", items, "now")


def day_item(day: int) -> ItineraryItem:
    return ItineraryItem(f"i{day}", day, f"Day {day}", start="08:00", end="20:00")


def size_of(png: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(png)).size


def has_dark_pixels(png: bytes) -> bool:
    low, _ = Image.open(io.BytesIO(png)).convert("L").getextrema()
    return low < 80


async def render(itinerary: Itinerary) -> RenderedItinerary:
    return await ItineraryRenderer().render(itinerary_view_of(itinerary))


async def test_a_short_plan_is_one_png_750_pixels_wide_in_the_light_colours() -> None:
    first = ItineraryItem("a", 1, "Kiyomizu", start="09:00", end="10:30")
    rendered = await render(itinerary_of(first, ItineraryItem("b", 2, "Free day")))
    assert rendered.omitted_day_count == 0
    assert all(png.startswith(PNG_SIGNATURE) for png in rendered.images)
    assert {size_of(png)[0] for png in rendered.images} == {IMAGE_WIDTH_PX}
    top_left = Image.open(io.BytesIO(rendered.images[0])).convert("RGB").getpixel((2, 2))
    assert top_left == (255, 255, 255)


async def test_each_day_adds_to_the_height_and_the_title_leads_the_first_image() -> None:
    one = await render(itinerary_of(day_item(1)))
    two = await render(itinerary_of(day_item(1), day_item(2)))
    one_height = sum(size_of(png)[1] for png in one.images)
    two_height = sum(size_of(png)[1] for png in two.images)
    assert two.omitted_day_count == 0 and two_height > one_height
    assert has_dark_pixels(two.images[0])


async def test_a_long_trip_is_cut_into_at_most_three_images_and_says_how_many_days_are_left() -> (
    None
):
    rendered = await render(itinerary_of(*(day_item(day) for day in range(1, 9))))
    assert len(rendered.images) == 3
    assert rendered.omitted_day_count == 5


async def test_a_title_with_markup_is_drawn_as_text() -> None:
    view = itinerary_view_of(itinerary_of(day_item(1)))
    view["title"] = "<img src='https://example.com/x.png'><b>bold</b>"
    rendered = await ItineraryRenderer().render(view)
    assert len(rendered.images) == 1
