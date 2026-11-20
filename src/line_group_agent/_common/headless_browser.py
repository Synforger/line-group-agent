"""A headless Chromium (Playwright) that opens on request and is closed with a close request
that is awaited, never killed.

Called by the itinerary picture renderer and by the simulator's screen capture, which both
draw pages without a window.
"""

from __future__ import annotations

from typing import Any


class BrowserUnavailableError(RuntimeError):
    """Playwright or its Chromium build is not installed."""


class HeadlessBrowser:
    """One headless Chromium; pages are made in contexts the caller closes."""

    def __init__(self) -> None:
        self._playwright: Any = None
        self._browser: Any = None

    async def open(self) -> None:
        """Start the browser."""
        try:
            from playwright.async_api import async_playwright
        except ImportError as error:
            raise BrowserUnavailableError("playwright is not installed") from error
        self._playwright = await async_playwright().start()
        try:
            self._browser = await self._playwright.chromium.launch()
        except Exception as error:  # the browser build may be missing; say how to get it
            await self._playwright.stop()
            self._playwright = None
            raise BrowserUnavailableError(
                "Chromium could not start; run `uv run playwright install chromium`"
            ) from error

    async def close(self) -> None:
        """Close the browser and wait until it is gone."""
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def new_context(self, **options: Any) -> Any:
        """Return a new browser context (Playwright's `new_context` options); the caller
        closes it."""
        return await self._browser.new_context(**options)

    async def __aenter__(self) -> HeadlessBrowser:
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
