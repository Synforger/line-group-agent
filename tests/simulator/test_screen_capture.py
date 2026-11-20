"""The browser side, with a real headless Chromium. Skipped where Playwright or its browser is
not installed (`uv run playwright install chromium`)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from line_group_agent.simulator.id_token import make_id_token
from line_group_agent.simulator.local_server import LocalServer
from line_group_agent.simulator.screen_capture import ScreenCapture, ScreensUnavailableError

pytestmark = pytest.mark.anyio
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PAGE = """<!doctype html><html><body><p id="problem"></p>
<script src="https://static.line-scdn.net/liff/edge/2/sdk.js"></script>
<script>
Promise.all([
  liff.init({liffId: "x"}),
  fetch("https://example.com/outside").then(() => "reached", () => "blocked"),
]).then(function (results) {
  var token = liff.getIDToken() ? "token" : "none";
  document.getElementById("problem").textContent =
    [liff.getDecodedIDToken().name, liff.isInClient(), token, results[1]].join(":");
});
</script></body></html>"""


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


async def test_a_page_opens_as_the_member_with_the_sdk_stand_in_and_no_outside_network(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    app = FastAPI()

    @app.get("/page")
    async def page() -> HTMLResponse:
        return HTMLResponse(PAGE)

    server = LocalServer(app)
    await server.start()
    try:
        picture = tmp_path / "screens" / "page.png"
        note = await screens.capture_liff(
            f"{server.base_url}/page", make_id_token("Uaki", "Aki"), picture
        )
    finally:
        await server.stop()
    assert picture.read_bytes().startswith(PNG_SIGNATURE)
    assert note == "the page says: Aki:true:token:blocked"


async def test_the_chat_page_is_photographed_whole(screens: ScreenCapture, tmp_path: Path) -> None:
    page = tmp_path / "chat.html"
    page.write_text("<!doctype html><body><div style='height:2000px'>long chat</div></body>")
    picture = tmp_path / "chat.png"
    await screens.capture_chat(page, picture)
    data = picture.read_bytes()
    assert data.startswith(PNG_SIGNATURE)
    height = int.from_bytes(data[20:24], "big")
    assert height >= 2000
