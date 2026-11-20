"""The two LIFF pages served by a small app whose API answers from canned values, for the tests
that open them in a browser: the page is the real file, the poll and the plan are made here."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from line_group_agent.liff.liff_page import load_itinerary_page, load_liff_page
from line_group_agent.simulator.id_token import make_id_token
from line_group_agent.simulator.local_server import LocalServer
from line_group_agent.simulator.screen_capture import LiffVisit, ScreenCapture

LIFF_ID = "1234567890-AbCdEfGh"
LINK_ID = "abcdefghij0123456789"
POLL_ADDRESS = f"/liff/?p={LINK_ID}"
ITINERARY_ADDRESS = f"/liff/itinerary?i={LINK_ID}"


def poll_app(labels: list[str], *, kind: str = "choice", multiple: bool = False) -> FastAPI:
    """Serve the voting page for a poll whose options are `labels`; the viewer is the only
    voter and a vote does what the real one does (a pick moves the vote, or toggles it)."""
    picked: set[int] = set()
    app = FastAPI()

    def view() -> dict[str, Any]:
        return {
            "question": "Where to?",
            "kind": kind,
            "multiple": multiple,
            "is_closed": False,
            "voter_count": 1 if picked else 0,
            "options": [
                {
                    "label": label,
                    "count": 1 if index in picked else 0,
                    "voters": ["Aki"] if index in picked else [],
                    "mine": index in picked,
                }
                for index, label in enumerate(labels)
            ],
        }

    @app.get("/liff/")
    async def page() -> HTMLResponse:
        return HTMLResponse(load_liff_page(LIFF_ID))

    @app.post("/liff/api/poll")
    async def show() -> dict[str, Any]:
        return view()

    @app.post("/liff/api/vote")
    async def vote(request: Request) -> dict[str, Any]:
        index = (await request.json())["option"]
        if kind == "date" or multiple:
            picked.symmetric_difference_update({index})
        else:
            picked.clear()
            picked.add(index)
        return view()

    return app


def itinerary_app(plan: dict[str, Any]) -> FastAPI:
    """Serve the itinerary page for the plan `plan`."""
    app = FastAPI()

    @app.get("/liff/itinerary")
    async def page() -> HTMLResponse:
        return HTMLResponse(load_itinerary_page(LIFF_ID))

    @app.post("/liff/api/itinerary")
    async def show() -> dict[str, Any]:
        return plan

    return app


def item(title: str, start: str | None = None, *, bottom_min: int | None = None) -> dict[str, Any]:
    """Return an item of a plan the way the API shapes it, timed when `start` is given."""
    shaped: dict[str, Any] = {
        "title": title,
        "start": start,
        "end": None,
        "place": None,
        "map_url": None,
        "note": None,
        "url": None,
    }
    if start is not None:
        hours, minutes = start.split(":")
        start_min = int(hours) * 60 + int(minutes)
        shaped |= {
            "start_min": start_min,
            "end_min": start_min + 60,
            "bottom_min": bottom_min if bottom_min is not None else start_min + 60,
            "column": 0,
            "columns": 1,
        }
    return shaped


def day_of(number: int, date: str | None, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a day of a plan: its items split into the untimed and the timed ones."""
    timed = [entry for entry in items if entry["start"] is not None]
    return {
        "day": number,
        "label": f"{number}日目",
        "date": date,
        "unscheduled": [entry for entry in items if entry["start"] is None],
        "scheduled": timed,
        "axis": (
            {"start_min": timed[0]["start_min"] - 60, "end_min": timed[-1]["bottom_min"] + 60}
            if timed
            else None
        ),
    }


def plan_of(days: list[dict[str, Any]], title: str = "Kyoto trip") -> dict[str, Any]:
    """Return a plan with these days."""
    return {"title": title, "start_date": None, "legacy_text": None, "days": days}


async def visit(
    screens: ScreenCapture,
    app: FastAPI,
    address: str,
    tmp_path: Path,
    *,
    click: Sequence[str] = (),
    environment: Mapping[str, Any] | None = None,
) -> LiffVisit:
    """Open the page at `address` of `app` as the member Aki, press what `click` names and
    return what the page said and sent."""
    server = LocalServer(app)
    await server.start()
    try:
        return await screens.capture_liff(
            f"{server.base_url}{address}",
            make_id_token("Uaki", "Aki"),
            tmp_path / "page.png",
            click=click,
            environment=environment,
        )
    finally:
        await server.stop()
