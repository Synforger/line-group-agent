"""Draw an itinerary as PNG images with the itinerary page itself.

The LIFF page (`liff/itinerary_page.html`) is opened in a headless Chromium in a mode that
draws every day one under the other from the view the page would have fetched, so an image
looks like the page, in the light appearance, at 750 pixels wide. No address outside the
machine is reachable while it draws. Called by `ItineraryImages`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from line_group_agent._common.headless_browser import BrowserUnavailableError, HeadlessBrowser
from line_group_agent.itinerary.image_slicing import slice_days
from line_group_agent.liff.liff_page import load_itinerary_page

PAGE_URL = "https://itinerary-image.invalid/"
VIEWPORT_WIDTH_PX = 375
VIEWPORT_HEIGHT_PX = 800
# Twice the page's width, so an image is 750 pixels wide and its text reads on a phone.
PIXEL_RATIO = 2
IMAGE_WIDTH_PX = VIEWPORT_WIDTH_PX * PIXEL_RATIO
# The axis takes 90 CSS pixels an hour, so a day from 8:00 to 20:00 is about 1300: an image
# holds one such day, or two shorter ones.
MAX_IMAGE_HEIGHT_PX = 2400
MAX_IMAGE_COUNT = 3
PAGE_TIMEOUT_MS = 15000
IMAGE_MODE_SCRIPT = "window.itineraryImageMode = true;"
DRAW_SCRIPT = "view => window.drawItineraryImage(view)"


class ItineraryRenderError(RuntimeError):
    """The images could not be drawn (no browser, or the page failed)."""


@dataclass(frozen=True)
class RenderedItinerary:
    """The PNG images, in order, and how many days after them did not fit."""

    images: list[bytes]
    omitted_day_count: int


class ItineraryRenderer:
    """Draws the images of one itinerary view; each call starts and closes its own browser."""

    async def render(self, view: dict[str, Any]) -> RenderedItinerary:
        """Return the images of `view` (what `itinerary_view_of` gives) with at least one
        day. Raises `ItineraryRenderError` when it cannot be drawn."""
        try:
            async with HeadlessBrowser() as browser:
                return await _draw(browser, view)
        except BrowserUnavailableError as error:
            raise ItineraryRenderError(str(error)) from error


async def _draw(browser: HeadlessBrowser, view: dict[str, Any]) -> RenderedItinerary:
    html = load_itinerary_page("")
    context = await browser.new_context(
        viewport={"width": VIEWPORT_WIDTH_PX, "height": VIEWPORT_HEIGHT_PX},
        device_scale_factor=PIXEL_RATIO,
        locale="ja-JP",
        color_scheme="light",
    )
    try:
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)
        problems: list[str] = []
        page.on("pageerror", lambda error: problems.append(str(error)))
        await page.route("**/*", lambda route: _answer(route, html))
        await page.add_init_script(IMAGE_MODE_SCRIPT)
        await page.goto(PAGE_URL)
        try:
            blocks = await page.evaluate(DRAW_SCRIPT, view)
        except Exception as error:
            raise ItineraryRenderError(f"the page could not draw the days: {error}") from error
        if problems:
            raise ItineraryRenderError(f"the page failed: {problems[0]}")
        await page.evaluate("document.fonts.ready.then(() => true)")
        slices = slice_days(
            [(block["top"], block["bottom"]) for block in blocks],
            max_height=MAX_IMAGE_HEIGHT_PX,
            max_count=MAX_IMAGE_COUNT,
        )
        images = [
            await page.screenshot(
                type="png",
                full_page=True,
                clip={
                    "x": 0,
                    "y": piece.top,
                    "width": VIEWPORT_WIDTH_PX,
                    "height": piece.bottom - piece.top,
                },
            )
            for piece in slices
        ]
    finally:
        await context.close()
    return RenderedItinerary(images, len(blocks) - sum(piece.day_count for piece in slices))


async def _answer(route: Any, html: str) -> None:
    """Serve the page at its made-up address and refuse every other address."""
    if route.request.url == PAGE_URL:
        await route.fulfill(body=html, content_type="text/html; charset=utf-8")
    else:
        await route.abort()
