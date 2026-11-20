"""A stand-in for LINE's HTTP APIs that the bot calls, answering as the scripted group.

It takes replies and pushes and keeps what they hold, tells the names and members of the
scripted group, serves the photos members "sent", and checks ID tokens made by `id_token`
(the LINE Login verify call). Run it on a local port with `LocalServer`; the bot is pointed
at it through its `line_api_base_url` setting. A reply token works once, as LINE's does.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from line_group_agent.simulator.id_token import read_id_token
from line_group_agent.simulator.scenario import Group

LINE_ISSUER = "https://access.line.me"
ID_TOKEN_LIFETIME_SECONDS = 3600
MAX_MESSAGES_PER_CALL = 5
HTTP_OK = 200
HTTP_ACCEPTED = 202
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
REPLY_KIND = "reply"
PUSH_KIND = "push"
OTHER_KIND = "other"
# In a `textV2` text: `{key}` is a placeholder, and a doubled brace is one literal brace.
TEXT_V2_PLACEHOLDER = re.compile(r"(?<!\{)\{(\w+)\}(?!\})")
TEXT_V2_STRAY_BRACE = re.compile(r"(?<!\{)\{(?!\{)|(?<!\})\}(?!\})")


@dataclass(frozen=True)
class RecordedCall:
    """One call the bot made: `kind` is `reply`, `push` or `other`; `body` the JSON it sent
    (None for a call without one); `target` the reply token or the push's receiver."""

    kind: str
    at_seconds: float
    method: str
    path: str
    status: int
    body: dict[str, Any] | None = None
    target: str = ""

    @property
    def messages(self) -> list[dict[str, Any]]:
        """The LINE messages the call carried (empty for any call that carries none)."""
        messages = (self.body or {}).get("messages")
        return messages if isinstance(messages, list) else []


class FakeLineServer:
    """The stand-in's web app (`app`) and its record of what the bot called."""

    def __init__(self, group: Group, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.group = group
        self.calls: list[RecordedCall] = []
        self._clock = clock
        self._started_at = clock()
        self._reply_tokens: set[str] = set()
        self._contents: dict[str, tuple[bytes, str]] = {}
        self.app = self._build_app()

    def elapsed_seconds(self) -> float:
        """Return the seconds since this stand-in started (the clock `RecordedCall` uses)."""
        return round(self._clock() - self._started_at, 3)

    def issue_reply_token(self, reply_token: str) -> None:
        """Let a reply with this token through once (the runner makes one for each event)."""
        self._reply_tokens.add(reply_token)

    def add_content(self, message_id: str, content: bytes, content_type: str) -> None:
        """Serve the bytes of a photo a member sent."""
        self._contents[message_id] = (content, content_type)

    def sent_calls(self) -> list[RecordedCall]:
        """Return the replies and pushes LINE took, in the order the bot made them."""
        return [
            call
            for call in self.calls
            if call.kind in (REPLY_KIND, PUSH_KIND) and call.status == 200
        ]

    def _problem_with(self, messages: object) -> str | None:
        return _problem_with(messages, {member.user_id for member in self.group.members})

    def _build_app(self) -> FastAPI:
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        group_id = self.group.id

        @app.post("/v2/bot/message/reply")
        async def reply(request: Request) -> Response:
            body = await _json_body(request)
            token = body.get("replyToken")
            if not isinstance(token, str) or token not in self._reply_tokens:
                return self._answer(
                    request,
                    REPLY_KIND,
                    HTTP_BAD_REQUEST,
                    body,
                    token or "",
                    {"message": "Invalid reply token"},
                )
            problem = self._problem_with(body.get("messages"))
            if problem is not None:
                return self._answer(
                    request, REPLY_KIND, HTTP_BAD_REQUEST, body, token, {"message": problem}
                )
            self._reply_tokens.discard(token)
            return self._answer(request, REPLY_KIND, HTTP_OK, body, token, {"sentMessages": []})

        @app.post("/v2/bot/message/push")
        async def push(request: Request) -> Response:
            body = await _json_body(request)
            to = body.get("to")
            problem = self._problem_with(body.get("messages"))
            if problem is not None or not isinstance(to, str):
                message = problem or "The property, 'to', must be specified."
                return self._answer(
                    request, PUSH_KIND, HTTP_BAD_REQUEST, body, "", {"message": message}
                )
            return self._answer(request, PUSH_KIND, HTTP_OK, body, to, {})

        @app.get("/v2/bot/group/{requested_group}/member/{user_id}")
        async def member(request: Request, requested_group: str, user_id: str) -> Response:
            person = next((m for m in self.group.members if m.user_id == user_id), None)
            if requested_group != group_id or person is None:
                return self._answer(request, OTHER_KIND, HTTP_NOT_FOUND, None, "", {})
            payload = {"displayName": person.name, "userId": person.user_id}
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", payload)

        @app.get("/v2/bot/group/{requested_group}/members/ids")
        async def member_ids(request: Request, requested_group: str) -> Response:
            if requested_group != group_id:
                return self._answer(request, OTHER_KIND, HTTP_NOT_FOUND, None, "", {})
            payload = {"memberIds": [person.user_id for person in self.group.members]}
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", payload)

        @app.get("/v2/bot/group/{requested_group}/members/count")
        async def member_count(request: Request, requested_group: str) -> Response:
            if requested_group != group_id:
                return self._answer(request, OTHER_KIND, HTTP_NOT_FOUND, None, "", {})
            payload = {"count": len(self.group.members)}
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", payload)

        @app.get("/v2/bot/group/{requested_group}/summary")
        async def summary(request: Request, requested_group: str) -> Response:
            if requested_group != group_id:
                return self._answer(request, OTHER_KIND, HTTP_NOT_FOUND, None, "", {})
            payload = {"groupId": group_id, "groupName": self.group.name}
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", payload)

        @app.post("/v2/bot/group/{requested_group}/leave")
        async def leave(request: Request, requested_group: str) -> Response:
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", {})

        @app.post("/v2/bot/chat/loading/start")
        async def loading(request: Request) -> Response:
            return self._answer(
                request, OTHER_KIND, HTTP_ACCEPTED, await _json_body(request), "", {}
            )

        @app.get("/v2/bot/message/quota")
        async def quota(request: Request) -> Response:
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", {"type": "none"})

        @app.get("/v2/bot/message/quota/consumption")
        async def consumption(request: Request) -> Response:
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", {"totalUsage": 0})

        @app.get("/v2/bot/message/{message_id}/content")
        async def content(request: Request, message_id: str) -> Response:
            found = self._contents.get(message_id)
            if found is None:
                return self._answer(request, OTHER_KIND, HTTP_NOT_FOUND, None, "", {})
            self._record(request, OTHER_KIND, HTTP_OK, None, "")
            return Response(found[0], media_type=found[1])

        @app.post("/oauth2/v2.1/verify")
        async def verify(request: Request) -> Response:
            form = parse_qs((await request.body()).decode("utf-8", errors="replace"))
            token = (form.get("id_token") or [""])[0]
            client_id = (form.get("client_id") or [""])[0]
            identity = read_id_token(token)
            if identity is None or not client_id:
                payload = {"error": "invalid_request", "error_description": "Invalid IdToken."}
                return self._answer(request, OTHER_KIND, HTTP_BAD_REQUEST, None, "", payload)
            now = int(time.time())
            claims = {
                "iss": LINE_ISSUER,
                "sub": identity[0],
                "aud": client_id,
                "exp": now + ID_TOKEN_LIFETIME_SECONDS,
                "iat": now,
                "name": identity[1],
            }
            return self._answer(request, OTHER_KIND, HTTP_OK, None, "", claims)

        return app

    def _answer(
        self,
        request: Request,
        kind: str,
        status: int,
        body: dict[str, Any] | None,
        target: str,
        payload: dict[str, Any],
    ) -> Response:
        self._record(request, kind, status, body, target)
        return JSONResponse(payload, status_code=status)

    def _record(
        self, request: Request, kind: str, status: int, body: dict[str, Any] | None, target: str
    ) -> None:
        self.calls.append(
            RecordedCall(
                kind=kind,
                at_seconds=self.elapsed_seconds(),
                method=request.method,
                path=request.url.path,
                status=status,
                body=body,
                target=target,
            )
        )


async def _json_body(request: Request) -> dict[str, Any]:
    try:
        body = json.loads(await request.body())
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _problem_with(messages: object, member_ids: set[str]) -> str | None:
    """Return why LINE would refuse these messages, or None when they pass."""
    if not isinstance(messages, list) or not messages:
        return "The request body has 1 error(s): messages must not be empty"
    if len(messages) > MAX_MESSAGES_PER_CALL:
        return f"The request body has 1 error(s): at most {MAX_MESSAGES_PER_CALL} messages"
    if not all(isinstance(message, dict) and message.get("type") for message in messages):
        return "The request body has 1 error(s): a message has no type"
    for message in messages:
        problem = _message_problem(message, member_ids)
        if problem is not None:
            return f"The request body has 1 error(s): {problem}"
    return None


def _message_problem(message: dict[str, Any], member_ids: set[str]) -> str | None:
    """Return why LINE would refuse a text v2 or a sticker message, or None."""
    if message["type"] == "sticker":
        ids = (message.get("packageId"), message.get("stickerId"))
        if not all(isinstance(value, str) and value for value in ids):
            return "packageId and stickerId must be strings"
    if message["type"] != "textV2":
        return None
    text, substitution = message.get("text"), message.get("substitution") or {}
    if not isinstance(text, str) or not text or not isinstance(substitution, dict):
        return "text must not be empty and substitution must be an object"
    if sum(1 for value in substitution.values() if _mentioned_user(value) is not None) > 20:
        return "at most 20 mentions"
    for value in substitution.values():
        user_id = _mentioned_user(value)
        if user_id is not None and user_id not in member_ids:
            return "a mentioned user is not in the group"
    keys = TEXT_V2_PLACEHOLDER.findall(text)
    if any(key not in substitution for key in keys) or TEXT_V2_STRAY_BRACE.search(
        TEXT_V2_PLACEHOLDER.sub("", text)
    ):
        return "a placeholder has no substitution or a brace is not paired"
    return None


def _mentioned_user(substitution: Any) -> str | None:
    if not isinstance(substitution, dict) or substitution.get("type") != "mention":
        return None
    mentionee = substitution.get("mentionee")
    user_id = mentionee.get("userId") if isinstance(mentionee, dict) else None
    return user_id if isinstance(user_id, str) else ""
