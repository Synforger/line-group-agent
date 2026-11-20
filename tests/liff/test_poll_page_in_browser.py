"""The voting page in a real browser with LINE's SDK stood in for: what it tells the talk after
a vote and what it shares. Skipped where Chromium is not installed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from line_group_agent.simulator.screen_capture import ScreenCapture
from tests.liff.page_app import LIFF_ID, LINK_ID, POLL_ADDRESS, poll_app, visit

pytestmark = pytest.mark.anyio
FIRST = "#options li:nth-child(1) button"
SECOND = "#options li:nth-child(2) button"
NOTIFY = "#notify"
SHARE = "#share"
REMEMBERED_OFF = {"storage": {"poll-notify-talk": "off"}}


def text_of(message: str) -> dict[str, str]:
    return {"type": "text", "text": message}


async def test_a_vote_tells_the_talk_in_the_voters_own_words(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens, poll_app(["Kyoto", "Osaka"]), POLL_ADDRESS, tmp_path, click=[SECOND]
    )
    assert seen.sent == [text_of("Osaka に入れたよ")]
    assert seen.note is None


async def test_a_date_pick_says_the_day_is_fine(screens: ScreenCapture, tmp_path: Path) -> None:
    app = poll_app(["11/23(月)", "11/24(火)"], kind="date", multiple=True)
    seen = await visit(screens, app, POLL_ADDRESS, tmp_path, click=[SECOND])
    assert seen.sent == [text_of("11/24(火) が行けるよ")]


async def test_pressing_the_option_already_picked_says_nothing_more(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens, poll_app(["Kyoto", "Osaka"]), POLL_ADDRESS, tmp_path, click=[FIRST, FIRST]
    )
    assert seen.sent == [text_of("Kyoto に入れたよ")]


async def test_taking_a_date_back_says_nothing(screens: ScreenCapture, tmp_path: Path) -> None:
    app = poll_app(["11/23(月)", "11/24(火)"], kind="date", multiple=True)
    seen = await visit(screens, app, POLL_ADDRESS, tmp_path, click=[FIRST, FIRST])
    assert seen.sent == [text_of("11/23(月) が行けるよ")]


async def test_moving_a_vote_tells_the_new_choice(screens: ScreenCapture, tmp_path: Path) -> None:
    seen = await visit(
        screens, poll_app(["Kyoto", "Osaka"]), POLL_ADDRESS, tmp_path, click=[FIRST, SECOND]
    )
    assert seen.sent == [text_of("Kyoto に入れたよ"), text_of("Osaka に入れたよ")]


async def test_with_the_check_off_the_vote_is_kept_and_the_talk_is_not_told(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens, poll_app(["Kyoto", "Osaka"]), POLL_ADDRESS, tmp_path, click=[NOTIFY, SECOND]
    )
    assert seen.sent == [] and seen.note is None


async def test_a_device_that_remembered_the_check_off_starts_with_it_off(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens,
        poll_app(["Kyoto", "Osaka"]),
        POLL_ADDRESS,
        tmp_path,
        click=[SECOND],
        environment=REMEMBERED_OFF,
    )
    assert seen.sent == [] and seen.note is None


@pytest.mark.parametrize(
    "environment",
    [
        {"inClient": False},
        {"context": "none"},
        {"chatMessageWrite": "prompt"},
        {"chatMessageWrite": "unavailable"},
    ],
    ids=["external browser", "not opened from a talk", "not consented", "scope not set"],
)
async def test_where_the_page_cannot_send_it_does_not_try(
    screens: ScreenCapture, tmp_path: Path, environment: dict[str, Any]
) -> None:
    voted = await visit(
        screens,
        poll_app(["Kyoto", "Osaka"]),
        POLL_ADDRESS,
        tmp_path,
        click=[SECOND],
        environment=environment,
    )
    assert voted.sent == [] and voted.note is None


async def test_where_the_page_cannot_send_the_check_is_hidden(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens,
        poll_app(["Kyoto"]),
        POLL_ADDRESS,
        tmp_path,
        click=[NOTIFY],
        environment={"inClient": False},
    )
    assert seen.note is not None and "could not press '#notify'" in seen.note


async def test_a_refusal_from_line_leaves_the_vote_and_says_nothing(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens,
        poll_app(["Kyoto", "Osaka"]),
        POLL_ADDRESS,
        tmp_path,
        click=[SECOND],
        environment={"sendMessagesFails": True},
    )
    assert seen.sent == [] and seen.note is None


async def test_the_page_shares_its_question_and_options_with_a_button_that_opens_it(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(screens, poll_app(["Kyoto", "Osaka"]), POLL_ADDRESS, tmp_path, click=[SHARE])
    [shared] = seen.shared
    assert shared["options"] == {"isMultiple": True}
    [message] = shared["messages"]
    assert message["type"] == "flex" and "Where to?" in message["altText"]
    body = message["contents"]["body"]["contents"]
    assert [part["text"] for part in body] == ["Where to?", "・Kyoto", "・Osaka"]
    [button] = message["contents"]["footer"]["contents"]
    assert button["action"] == {
        "type": "uri",
        "label": "投票を開く",
        "uri": f"https://liff.line.me/{LIFF_ID}?p={LINK_ID}",
    }
    assert seen.sent == []


async def test_without_the_share_target_picker_there_is_no_share_button(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens,
        poll_app(["Kyoto"]),
        POLL_ADDRESS,
        tmp_path,
        click=[SHARE],
        environment={"shareTargetPicker": False},
    )
    assert seen.shared == []
    assert seen.note is not None and "could not press '#share'" in seen.note
