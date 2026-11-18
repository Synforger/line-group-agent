"""A voting page wired the way the service builder wires it, over a temporary folder, a fake
LINE and a fake LINE Login, for the tests of its routes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from line_group_agent.liff.liff_members import LiffMembers
from line_group_agent.liff.liff_page import load_liff_page
from line_group_agent.liff.liff_polls import LiffPolls
from line_group_agent.liff.liff_router import build_liff_router
from line_group_agent.liff.request_limiter import RequestLimiter
from line_group_agent.line_api.line_client import LineApiError
from line_group_agent.polls.poll import Poll
from line_group_agent.polls.poll_book import PollBook
from tests.fakes import FakeLine
from tests.world import GROUP, Clock

LOGIN_CHANNEL = "1234567890"
LIFF_ID = "1234567890-AbCdEfGh"
ISSUER = "https://access.line.me"
MEMBER = "Umember"
OTHER_MEMBER = "Uother"
OUTSIDER = "Uoutsider"
GOOD_TOKEN = "token-of-member"
OTHER_TOKEN = "token-of-other"


class FakeLogin:
    """Stands in for LINE Login's verify call: a token it knows gives its claims, any other
    token is refused (a 400), and `error_status` makes every call fail like a LINE outage."""

    def __init__(self) -> None:
        self.claims_by_token: dict[str, dict[str, Any]] = {}
        self.error_status: int | None = None
        self.calls: list[tuple[str, str]] = []

    async def verify_id_token(self, id_token: str, client_id: str) -> dict[str, Any] | None:
        self.calls.append((id_token, client_id))
        if self.error_status is not None:
            raise LineApiError("verify", self.error_status)
        return self.claims_by_token.get(id_token)

    async def close(self) -> None:
        return None


def claims_of(user_id: str, clock: Clock, **changes: Any) -> dict[str, Any]:
    """Return the claims of a good token of this member, valid for an hour."""
    claims: dict[str, Any] = {
        "iss": ISSUER,
        "sub": user_id,
        "aud": LOGIN_CHANNEL,
        "exp": clock().timestamp() + 3600,
    }
    claims.update(changes)
    return claims


@dataclass
class Liff:
    client: TestClient
    polls: PollBook
    login: FakeLogin
    line: FakeLine
    clock: Clock
    poll: Poll
    seconds: list[float]

    def post(self, path: str, body: Any, token: str | None = GOOD_TOKEN) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        return self.client.post(path, content=payload, headers=headers)

    def show(self, token: str | None = GOOD_TOKEN, link_id: str | None = None) -> Any:
        return self.post(
            "/liff/api/poll", {"p": self.poll.link_id if link_id is None else link_id}, token
        )

    def vote(self, option: object, token: str | None = GOOD_TOKEN) -> Any:
        return self.post("/liff/api/vote", {"p": self.poll.link_id, "option": option}, token)

    def advance(self, seconds: float) -> None:
        self.seconds[0] += seconds


def build_liff(
    tmp_path: Path,
    *,
    multiple: bool = False,
    allowed_groups: frozenset[str] = frozenset({GROUP}),
    max_per_minute: int = 60,
    max_body_bytes: int = 1024,
) -> Liff:
    """Make a poll `Which?` (Kyoto, Osaka) in the group and a page for it. `MEMBER` and
    `OTHER_MEMBER` are in the group; each has a good token (`GOOD_TOKEN`, `OTHER_TOKEN`).
    `liff.advance` moves the clock the limiter and the member memory read."""
    clock = Clock()
    polls = PollBook(tmp_path, clock)
    poll = polls.create(GROUP, "Which?", ["Kyoto", "Osaka"], multiple=multiple)
    line = FakeLine(
        members={MEMBER: True, OTHER_MEMBER: True},
        names={MEMBER: "Aki", OTHER_MEMBER: "Ben"},
    )
    login = FakeLogin()
    login.claims_by_token[GOOD_TOKEN] = claims_of(MEMBER, clock)
    login.claims_by_token[OTHER_TOKEN] = claims_of(OTHER_MEMBER, clock)
    seconds = [0.0]
    service = LiffPolls(
        polls,
        login,  # type: ignore[arg-type]
        LiffMembers(line, clock=lambda: seconds[0]),
        RequestLimiter(max_per_minute, clock=lambda: seconds[0]),
        login_channel_id=LOGIN_CHANNEL,
        is_group_allowed=lambda group_id: group_id in allowed_groups,
        clock=clock,
    )
    app = FastAPI()
    app.include_router(
        build_liff_router(load_liff_page(LIFF_ID), service, max_body_bytes=max_body_bytes)
    )
    return Liff(TestClient(app), polls, login, line, clock, poll, seconds)
