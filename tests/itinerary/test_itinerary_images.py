from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.itinerary.itinerary import Itinerary, ItineraryItem
from line_group_agent.itinerary.itinerary_image_store import ItineraryImageStore
from line_group_agent.itinerary.itinerary_images import ItineraryImages
from line_group_agent.itinerary.itinerary_renderer import (
    ItineraryRenderer,
    ItineraryRenderError,
    RenderedItinerary,
)

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=timezone(timedelta(hours=9)))
BASE = "https://bot.example"
ITINERARY = Itinerary("Trip", "2026-11-23", (ItineraryItem("a", 1, "Walk", start="09:00"),), "now")


class FakeRenderer(ItineraryRenderer):
    def __init__(self, result: RenderedItinerary | Exception) -> None:
        self.result = result
        self.views: list[dict[str, Any]] = []

    async def render(self, view: dict[str, Any]) -> RenderedItinerary:
        self.views.append(view)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def images_of(tmp_path: Path, result: RenderedItinerary | Exception) -> ItineraryImages:
    store = ItineraryImageStore(tmp_path, lambda: NOW)
    return ItineraryImages(FakeRenderer(result), store, public_base_url=BASE)


def test_each_image_is_kept_and_given_an_address_below_the_public_one(tmp_path: Path) -> None:
    images = images_of(tmp_path, RenderedItinerary([b"one", b"two"], 2))
    made = images.create_blocking("Cgroup", ITINERARY)
    assert made is not None and made.omitted_day_count == 2
    assert all(url.startswith(f"{BASE}/liff/media/") and url.endswith(".png") for url in made.urls)
    names = [url.rsplit("/", 1)[1] for url in made.urls]
    assert [images.store.read(name) for name in names] == [b"one", b"two"]


def test_the_view_the_page_gets_is_what_is_drawn(tmp_path: Path) -> None:
    images = images_of(tmp_path, RenderedItinerary([b"x"], 0))
    images.create_blocking("Cgroup", ITINERARY)
    assert isinstance(images.renderer, FakeRenderer)
    assert images.renderer.views[0]["title"] == "Trip"
    assert images.renderer.views[0]["days"][0]["label"] == "11/23(月) 1日目"


@pytest.mark.parametrize("failure", [ItineraryRenderError("no browser"), OSError("disk")])
def test_a_drawing_that_fails_gives_none_and_a_log_line(
    tmp_path: Path, failure: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    images = images_of(tmp_path, failure)
    assert images.create_blocking("Cgroup", ITINERARY) is None
    assert "could not draw" in caplog.text
