"""The HTTP side: the endpoint `POST /line/webhook` that LINE calls, and any routers given
(the voting page's).

Built by the service builder. The webhook caps the body size, checks the signature
on the raw bytes before reading anything, queues the events and answers 200 at once;
the events are handled afterwards by the dispatcher.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol

from fastapi import APIRouter, FastAPI, Request, Response

from line_group_agent.webhook.capped_body import read_capped_body
from line_group_agent.webhook.signature import is_valid_signature

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/line/webhook"
SIGNATURE_HEADER = "x-line-signature"


class Background(Protocol):
    """A task that runs while the app is up (the patrol)."""

    def start(self) -> None: ...

    async def stop(self) -> None: ...


class EventSink(Protocol):
    """Where verified events go (the event dispatcher)."""

    def start(self) -> None: ...

    async def stop(self) -> None: ...

    def add_events(self, events: list[Any]) -> None: ...


def create_app(
    channel_secret: str,
    max_body_bytes: int,
    sink: EventSink,
    *,
    on_close: list[Callable[[], Awaitable[None]]] | None = None,
    background: list[Background] | None = None,
    routers: list[APIRouter] | None = None,
) -> FastAPI:
    """Return the web app. `background` tasks run while it is up; `on_close` runs at
    shutdown (to close API clients); `routers` add their routes beside the webhook."""

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        sink.start()
        for task in background or []:
            task.start()
        try:
            yield
        finally:
            for task in background or []:
                await task.stop()
            await sink.stop()
            for close in on_close or []:
                await close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.post(WEBHOOK_PATH)
    async def receive(request: Request) -> Response:
        body = await read_capped_body(request, max_body_bytes)
        if body is None:
            logger.warning("webhook: body over %d bytes refused", max_body_bytes)
            return Response(status_code=413)
        if not is_valid_signature(body, request.headers.get(SIGNATURE_HEADER), channel_secret):
            logger.warning("webhook: bad or missing signature")
            return Response(status_code=401)
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return Response(status_code=400)
        events = payload.get("events") if isinstance(payload, dict) else None
        if isinstance(events, list):
            sink.add_events(events)
        return Response(status_code=200)

    for router in routers or []:
        app.include_router(router)
    return app
