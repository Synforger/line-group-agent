"""The routes of the LIFF pages: `GET /liff/` (the voting page, no group content) and
`POST /liff/api/poll` and `POST /liff/api/vote` (the poll's content, for a verified member);
with an itinerary service also `GET /liff/itinerary` (the itinerary page) and
`POST /liff/api/itinerary` (the plan, for a verified member).

The ID token comes in the `Authorization: Bearer` header, the link id and the option
in a small JSON body; the last address of `X-Forwarded-For` (the one the reverse proxy in
front appends; the earlier ones are written by the caller) names where a request came from.
Every answer says `Cache-Control: no-store`; a refusal is a bare status
with a one-word error and no detail. Built by the service builder and added to the web app.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from line_group_agent.liff.liff_itineraries import LiffItineraries
from line_group_agent.liff.liff_polls import LiffPolls
from line_group_agent.liff.liff_refusal import (
    HTTP_BAD_REQUEST,
    HTTP_FORBIDDEN,
    HTTP_TOO_MANY_REQUESTS,
    HTTP_UNAUTHORIZED,
    HTTP_UNAVAILABLE,
    LiffRefusal,
)
from line_group_agent.webhook.capped_body import read_capped_body

PAGE_PATH = "/liff/"
POLL_PATH = "/liff/api/poll"
VOTE_PATH = "/liff/api/vote"
ITINERARY_PAGE_PATH = "/liff/itinerary"
ITINERARY_PATH = "/liff/api/itinerary"
HTTP_PAYLOAD_TOO_LARGE = 413
BEARER_PREFIX = "bearer "
MAX_TOKEN_CHARS = 4096
MAX_SOURCE_CHARS = 64
ERROR_WORDS = {
    HTTP_BAD_REQUEST: "bad_request",
    HTTP_UNAUTHORIZED: "unauthorized",
    HTTP_FORBIDDEN: "forbidden",
    HTTP_PAYLOAD_TOO_LARGE: "too_large",
    HTTP_TOO_MANY_REQUESTS: "too_many_requests",
    HTTP_UNAVAILABLE: "unavailable",
}
# Nothing here may be cached, and the page's address (which holds the link id) stays
# out of the Referer of anything the page loads.
SAFE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


Action = Callable[[str, dict[str, Any], str | None], Awaitable[dict[str, Any]]]


def build_liff_router(
    page: str,
    polls: LiffPolls,
    *,
    max_body_bytes: int,
    itinerary_page: str | None = None,
    itineraries: LiffItineraries | None = None,
) -> APIRouter:
    """Return the routes of the voting page, serving `page` and answering for `polls`; given
    `itinerary_page` and `itineraries`, those of the itinerary page as well."""
    router = APIRouter()

    async def show_action(token: str, body: dict[str, Any], source: str | None) -> dict[str, Any]:
        return await polls.show(token, _link_id_of(body), source)

    async def vote_action(token: str, body: dict[str, Any], source: str | None) -> dict[str, Any]:
        option = body.get("option")
        if isinstance(option, bool) or not isinstance(option, int):
            raise LiffRefusal(HTTP_BAD_REQUEST)
        return await polls.vote(token, _link_id_of(body), option, source)

    @router.get(PAGE_PATH)
    async def show_page() -> Response:
        return HTMLResponse(page, headers=SAFE_HEADERS)

    @router.post(POLL_PATH)
    async def show_poll(request: Request) -> Response:
        return await _answer(request, max_body_bytes, show_action)

    @router.post(VOTE_PATH)
    async def vote(request: Request) -> Response:
        return await _answer(request, max_body_bytes, vote_action)

    if itinerary_page is not None and itineraries is not None:
        _add_itinerary_routes(router, itinerary_page, itineraries, max_body_bytes)
    return router


def _add_itinerary_routes(
    router: APIRouter, page: str, itineraries: LiffItineraries, max_body_bytes: int
) -> None:
    async def show_action(token: str, body: dict[str, Any], source: str | None) -> dict[str, Any]:
        return await itineraries.show(token, _link_id_of(body, "i"), source)

    @router.get(ITINERARY_PAGE_PATH)
    async def show_page() -> Response:
        return HTMLResponse(page, headers=SAFE_HEADERS)

    @router.post(ITINERARY_PATH)
    async def show_itinerary(request: Request) -> Response:
        return await _answer(request, max_body_bytes, show_action)


async def _answer(request: Request, max_body_bytes: int, action: Action) -> Response:
    try:
        token = _token_of(request)
        raw = await read_capped_body(request, max_body_bytes)
        if raw is None:
            raise LiffRefusal(HTTP_PAYLOAD_TOO_LARGE)
        return _json(200, await action(token, _object_of(raw), _source_of(request)))
    except LiffRefusal as refusal:
        return _json(refusal.status, {"error": ERROR_WORDS.get(refusal.status, "refused")})


def _token_of(request: Request) -> str:
    header = request.headers.get("authorization", "")
    token = header[len(BEARER_PREFIX) :].strip() if header.lower().startswith(BEARER_PREFIX) else ""
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise LiffRefusal(HTTP_UNAUTHORIZED)
    return token


def _source_of(request: Request) -> str | None:
    """Return the last address of `X-Forwarded-For`, the one the proxy in front appended,
    or None when there is none (or it is longer than any address). The earlier addresses
    come from the caller and could be anything."""
    last = request.headers.get("x-forwarded-for", "").split(",")[-1].strip()
    return last if 0 < len(last) <= MAX_SOURCE_CHARS else None


def _object_of(raw: bytes) -> dict[str, Any]:
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise LiffRefusal(HTTP_BAD_REQUEST) from error
    if not isinstance(body, dict):
        raise LiffRefusal(HTTP_BAD_REQUEST)
    return body


def _link_id_of(body: dict[str, Any], key: str = "p") -> str:
    link_id = body.get(key)
    if not isinstance(link_id, str):
        raise LiffRefusal(HTTP_BAD_REQUEST)
    return link_id


def _json(status: int, content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content, status_code=status, headers=SAFE_HEADERS)
