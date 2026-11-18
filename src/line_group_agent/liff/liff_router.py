"""The routes of the voting page: `GET /liff/` (the page, no group content) and
`POST /liff/api/poll` and `POST /liff/api/vote` (the poll's content, for a verified member).

The ID token comes in the `Authorization: Bearer` header, the poll's link id and the option
in a small JSON body. Every answer says `Cache-Control: no-store`; a refusal is a bare status
with a one-word error and no detail. Built by the service builder and added to the web app.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from line_group_agent.liff.liff_polls import (
    HTTP_BAD_REQUEST,
    HTTP_FORBIDDEN,
    HTTP_TOO_MANY_REQUESTS,
    HTTP_UNAUTHORIZED,
    HTTP_UNAVAILABLE,
    LiffPolls,
    LiffRefusal,
)
from line_group_agent.webhook.capped_body import read_capped_body

PAGE_PATH = "/liff/"
POLL_PATH = "/liff/api/poll"
VOTE_PATH = "/liff/api/vote"
HTTP_PAYLOAD_TOO_LARGE = 413
BEARER_PREFIX = "bearer "
MAX_TOKEN_CHARS = 4096
ERROR_WORDS = {
    HTTP_BAD_REQUEST: "bad_request",
    HTTP_UNAUTHORIZED: "unauthorized",
    HTTP_FORBIDDEN: "forbidden",
    HTTP_PAYLOAD_TOO_LARGE: "too_large",
    HTTP_TOO_MANY_REQUESTS: "too_many_requests",
    HTTP_UNAVAILABLE: "unavailable",
}
# Nothing here may be cached, and the page's address (which holds the poll's link id) stays
# out of the Referer of anything the page loads.
SAFE_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}


Action = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def build_liff_router(page: str, polls: LiffPolls, *, max_body_bytes: int) -> APIRouter:
    """Return the routes of the voting page, serving `page` and answering for `polls`."""
    router = APIRouter()

    async def show_action(token: str, body: dict[str, Any]) -> dict[str, Any]:
        return await polls.show(token, _link_id_of(body))

    async def vote_action(token: str, body: dict[str, Any]) -> dict[str, Any]:
        option = body.get("option")
        if isinstance(option, bool) or not isinstance(option, int):
            raise LiffRefusal(HTTP_BAD_REQUEST)
        return await polls.vote(token, _link_id_of(body), option)

    @router.get(PAGE_PATH)
    async def show_page() -> Response:
        return HTMLResponse(page, headers=SAFE_HEADERS)

    @router.post(POLL_PATH)
    async def show_poll(request: Request) -> Response:
        return await _answer(request, max_body_bytes, show_action)

    @router.post(VOTE_PATH)
    async def vote(request: Request) -> Response:
        return await _answer(request, max_body_bytes, vote_action)

    return router


async def _answer(request: Request, max_body_bytes: int, action: Action) -> Response:
    try:
        token = _token_of(request)
        raw = await read_capped_body(request, max_body_bytes)
        if raw is None:
            raise LiffRefusal(HTTP_PAYLOAD_TOO_LARGE)
        return _json(200, await action(token, _object_of(raw)))
    except LiffRefusal as refusal:
        return _json(refusal.status, {"error": ERROR_WORDS.get(refusal.status, "refused")})


def _token_of(request: Request) -> str:
    header = request.headers.get("authorization", "")
    token = header[len(BEARER_PREFIX) :].strip() if header.lower().startswith(BEARER_PREFIX) else ""
    if not token or len(token) > MAX_TOKEN_CHARS:
        raise LiffRefusal(HTTP_UNAUTHORIZED)
    return token


def _object_of(raw: bytes) -> dict[str, Any]:
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise LiffRefusal(HTTP_BAD_REQUEST) from error
    if not isinstance(body, dict):
        raise LiffRefusal(HTTP_BAD_REQUEST)
    return body


def _link_id_of(body: dict[str, Any]) -> str:
    link_id = body.get("p")
    if not isinstance(link_id, str):
        raise LiffRefusal(HTTP_BAD_REQUEST)
    return link_id


def _json(status: int, content: dict[str, Any]) -> JSONResponse:
    return JSONResponse(content, status_code=status, headers=SAFE_HEADERS)
