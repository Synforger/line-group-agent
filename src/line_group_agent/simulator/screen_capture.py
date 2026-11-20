"""Take pictures of pages in a headless Chromium (Playwright): the chat page and the LIFF
pages the bot serves.

LINE's LIFF SDK is replaced by a small stand-in (`liff_sdk_stub.js`) so a page opens outside
LINE as a chosen member, and every address outside this machine is refused so a page cannot
reach the network. The stand-in writes down what a page asked it to send or share, and a
visit can press one thing in the page first. Called by the simulation. The browser is closed
with a close request and awaited, never killed.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from line_group_agent._common.headless_browser import BrowserUnavailableError, HeadlessBrowser
from line_group_agent.simulator.id_token import read_id_token

LIFF_SDK_URL = "https://static.line-scdn.net/liff/edge/2/sdk.js"
STUB_FILE = Path(__file__).with_name("liff_sdk_stub.js")
LOCAL_ORIGIN = "http://127.0.0.1"
PHONE_WIDTH = 390
PHONE_HEIGHT = 844
LIFF_SCALE = 2
CHAT_SCALE = 1
PAGE_TIMEOUT_MS = 20000
SETTLE_MS = 600
CLICK_TIMEOUT_MS = 3000
PROBLEM_SCRIPT = "(document.getElementById('problem') || {}).textContent || ''"
CALLS_SCRIPT = "window.__liffCalls || {sent: [], shared: []}"
STUB_CONFIG_SCRIPT = "window.__liffStubConfig = {config};"


class ScreensUnavailableError(RuntimeError):
    """Playwright or its browser is not installed."""


@dataclass
class LiffVisit:
    """What a visit to a LIFF page left: `note` is what the page said was wrong (or the errors
    it logged), None when it looked well; `sent` the messages the page had `liff.sendMessages`
    send as the member; `shared` what it passed to `liff.shareTargetPicker`, each as
    `{"messages": [...], "options": {...}}`."""

    note: str | None
    sent: list[dict[str, Any]] = field(default_factory=list)
    shared: list[dict[str, Any]] = field(default_factory=list)


class ScreenCapture:
    """A headless Chromium that takes full-page pictures at a phone's width."""

    def __init__(self) -> None:
        self._browser = HeadlessBrowser()

    async def open(self) -> None:
        """Start the browser."""
        try:
            await self._browser.open()
        except BrowserUnavailableError as error:
            raise ScreensUnavailableError(str(error)) from error

    async def close(self) -> None:
        """Close the browser and wait until it is gone."""
        await self._browser.close()

    async def __aenter__(self) -> ScreenCapture:
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def capture_chat(self, page_file: Path, png_file: Path) -> None:
        """Take a picture of the whole chat page written to `page_file`."""
        context = await self._browser.new_context(
            viewport={"width": PHONE_WIDTH, "height": PHONE_HEIGHT}, device_scale_factor=CHAT_SCALE
        )
        try:
            page = await context.new_page()
            await page.goto(page_file.resolve().as_uri(), timeout=PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(SETTLE_MS)
            await page.screenshot(path=str(png_file), full_page=True)
        finally:
            await context.close()

    async def capture_liff(
        self,
        page_url: str,
        id_token: str,
        png_file: Path,
        *,
        click: Sequence[str] = (),
        environment: Mapping[str, Any] | None = None,
    ) -> LiffVisit:
        """Open a LIFF page of the bot as the member the token names, press the elements the CSS
        selectors in `click` name one after the other, take a picture of the whole page and
        return what the visit left. `environment` changes where the page seems to be open
        (see `liff_sdk_stub.js`)."""
        context = await self._browser.new_context(
            viewport={"width": PHONE_WIDTH, "height": PHONE_HEIGHT},
            device_scale_factor=LIFF_SCALE,
            locale="ja-JP",
        )
        problems: list[str] = []
        try:
            page = await context.new_page()
            page.on("pageerror", lambda error: problems.append(f"page error: {error}"))
            await page.route(lambda url: not url.startswith(LOCAL_ORIGIN), _refuse)
            stub = _stub_for(id_token)
            await page.route(
                LIFF_SDK_URL,
                lambda route: route.fulfill(body=stub, content_type="application/javascript"),
            )
            if environment:
                await page.add_init_script(
                    STUB_CONFIG_SCRIPT.format(config=json.dumps(dict(environment)))
                )
            await page.goto(page_url, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
            await page.wait_for_timeout(SETTLE_MS)
            for selector in click:
                if not await self._press(page, selector, problems):
                    break
            said = str(await page.evaluate(PROBLEM_SCRIPT)).strip()
            if said:
                problems.insert(0, f"the page says: {said}")
            calls = await page.evaluate(CALLS_SCRIPT)
            png_file.parent.mkdir(parents=True, exist_ok=True)
            await page.screenshot(path=str(png_file), full_page=True)
        finally:
            await context.close()
        return LiffVisit("; ".join(problems) or None, calls["sent"], calls["shared"])

    async def _press(self, page: Any, selector: str, problems: list[str]) -> bool:
        """Press the element and wait for the page to settle; False when it could not be pressed."""
        try:
            await page.locator(selector).first.click(timeout=CLICK_TIMEOUT_MS)
        except Exception as error:  # Playwright's own errors (a missing or covered element)
            problems.append(f"could not press {selector!r} ({type(error).__name__})")
            return False
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(SETTLE_MS)
        return True


async def _refuse(route: Any) -> None:
    await route.abort()


def _stub_for(id_token: str) -> str:
    identity = read_id_token(id_token)
    claims = {"sub": identity[0], "name": identity[1]} if identity else {}
    return (
        STUB_FILE.read_text(encoding="utf-8")
        .replace("__ID_TOKEN__", json.dumps(id_token))
        .replace("__CLAIMS__", json.dumps(claims, ensure_ascii=False))
    )
