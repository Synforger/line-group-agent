"""Shared pytest settings: async tests run on asyncio through `anyio`, and `screens` is a
headless Chromium for the tests that open pages for real (skipped where Playwright or its
browser is not installed: `uv run playwright install chromium`)."""

from collections.abc import AsyncIterator

import pytest

from line_group_agent.simulator.screen_capture import ScreenCapture, ScreensUnavailableError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def screens() -> AsyncIterator[ScreenCapture]:
    capture = ScreenCapture()
    try:
        await capture.open()
    except ScreensUnavailableError as error:
        pytest.skip(str(error))
    try:
        yield capture
    finally:
        await capture.close()
