"""An itinerary page wired the way the service builder wires it, over a temporary folder, a fake
member lookup and a fake LINE Login, for the tests of its routes. Two groups each have an
itinerary; `MEMBER` is in the first one only."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from line_group_agent.itinerary.itinerary_book import ItineraryBook
from line_group_agent.liff.liff_itineraries import LiffItineraries
from line_group_agent.liff.liff_members import LiffMembers
from line_group_agent.liff.liff_page import load_itinerary_page, load_liff_page
from line_group_agent.liff.liff_polls import LiffPolls
from line_group_agent.liff.liff_router import build_liff_router
from line_group_agent.liff.request_limiter import RequestLimiter
from line_group_agent.liff.verify_failure_limiter import VerifyFailureLimiter
from line_group_agent.polls.poll_book import PollBook
from tests.liff.liff_harness import (
    GOOD_TOKEN,
    LIFF_ID,
    LOGIN_CHANNEL,
    MEMBER,
    FakeLogin,
    claims_of,
)
from tests.world import GROUP, Clock

OTHER_GROUP = "Cother"


class GroupDirectory:
    """Stands in for LINE's member lookup: who is in which group. With `is_unclear` set LINE
    gives no clear answer."""

    def __init__(self, members_by_group: dict[str, set[str]]) -> None:
        self.members_by_group = members_by_group
        self.is_unclear = False
        self.asked: list[tuple[str, str]] = []

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        self.asked.append((group_id, user_id))
        if self.is_unclear:
            return None
        return user_id in self.members_by_group.get(group_id, set())

    async def get_member_name(self, group_id: str, user_id: str) -> str | None:
        return None


@dataclass
class ItineraryLiff:
    client: TestClient
    itineraries: ItineraryBook
    login: FakeLogin
    line: GroupDirectory
    clock: Clock
    link_id: str
    other_link_id: str

    def show(self, token: str | None = GOOD_TOKEN, link_id: str | None = None) -> Any:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        body = json.dumps({"i": self.link_id if link_id is None else link_id}).encode()
        return self.client.post("/liff/api/itinerary", content=body, headers=headers)


def build_itinerary_liff(
    tmp_path: Path,
    *,
    allowed_groups: frozenset[str] = frozenset({GROUP, OTHER_GROUP}),
    max_per_minute: int = 60,
) -> ItineraryLiff:
    clock = Clock()
    itineraries = ItineraryBook(tmp_path, clock)
    itineraries.change_trip(GROUP, {"title": "Kyoto trip", "start_date": "2026-11-23"})
    itineraries.add_item(GROUP, day=1, title="Kiyomizu", start="09:00", end="10:30", place="Kyoto")
    itineraries.add_item(GROUP, day=1, title="Lunch", start="10:00", end="11:00")
    itineraries.add_item(GROUP, day=2, title="Free day")
    itineraries.add_item(OTHER_GROUP, day=1, title="Secret plan of the other group", start="09:00")
    link_id = itineraries.link_id(GROUP)
    other_link_id = itineraries.link_id(OTHER_GROUP)
    assert link_id and other_link_id
    line = GroupDirectory({GROUP: {MEMBER}})
    login = FakeLogin()
    login.claims_by_token[GOOD_TOKEN] = claims_of(MEMBER, clock)
    seconds = [0.0]
    members = LiffMembers(line, clock=lambda: seconds[0])
    limiter = RequestLimiter(max_per_minute, clock=lambda: seconds[0])
    failures = VerifyFailureLimiter(30, 10, clock=lambda: seconds[0])
    polls = LiffPolls(
        PollBook(tmp_path, clock),
        login,  # type: ignore[arg-type]
        members,
        limiter,
        failures,
        login_channel_id=LOGIN_CHANNEL,
        is_group_allowed=lambda group_id: group_id in allowed_groups,
        clock=clock,
    )
    service = LiffItineraries(
        itineraries,
        polls.gate,
        members,
        is_group_allowed=lambda group_id: group_id in allowed_groups,
    )
    app = FastAPI()
    app.include_router(
        build_liff_router(
            load_liff_page(LIFF_ID),
            polls,
            max_body_bytes=1024,
            itinerary_page=load_itinerary_page(LIFF_ID),
            itineraries=service,
        )
    )
    return ItineraryLiff(TestClient(app), itineraries, login, line, clock, link_id, other_link_id)
