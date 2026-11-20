"""The itinerary page in a real browser with LINE's SDK stood in for: what it shares. Skipped
where Chromium is not installed."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from line_group_agent.simulator.screen_capture import ScreenCapture
from tests.liff.page_app import (
    ITINERARY_ADDRESS,
    LIFF_ID,
    LINK_ID,
    day_of,
    item,
    itinerary_app,
    plan_of,
    visit,
)

pytestmark = pytest.mark.anyio
SHARE = "#share"
MINUTES_PER_DAY = 24 * 60


def month_day(day: date) -> str:
    return f"{day.month}/{day.day}"


async def share_of(screens: ScreenCapture, tmp_path: Path, plan: dict) -> dict:
    seen = await visit(screens, itinerary_app(plan), ITINERARY_ADDRESS, tmp_path, click=[SHARE])
    [shared] = seen.shared
    assert shared["options"] == {"isMultiple": True}
    [message] = shared["messages"]
    return message


def lines_of(message: dict) -> list[str]:
    return [part["text"] for part in message["contents"]["body"]["contents"]]


async def test_the_page_shares_the_trips_name_and_the_next_three_items(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    today = date.today()
    plan = plan_of(
        [
            day_of(1, (today - timedelta(days=1)).isoformat(), [item("Gone", "10:00")]),
            day_of(
                2,
                today.isoformat(),
                [
                    item("Breakfast", "00:00", bottom_min=0),
                    item("Souvenirs"),
                    item("Lunch", "23:00", bottom_min=MINUTES_PER_DAY),
                ],
            ),
            day_of(
                3,
                (today + timedelta(days=1)).isoformat(),
                [item("Temple", "09:00"), item("Dinner", "18:00")],
            ),
        ]
    )
    message = await share_of(screens, tmp_path, plan)
    assert lines_of(message) == [
        "Kyoto trip",
        "次の予定",
        f"{month_day(today)} 時間未定 Souvenirs",
        f"{month_day(today)} 23:00 Lunch",
        f"{month_day(today + timedelta(days=1))} 09:00 Temple",
    ]
    assert message["altText"] == "予定表: Kyoto trip"


async def test_the_button_opens_the_itinerary_page_of_the_trip(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    message = await share_of(
        screens, tmp_path, plan_of([day_of(1, None, [item("Temple", "09:00")])])
    )
    [button] = message["contents"]["footer"]["contents"]
    assert button["action"] == {
        "type": "uri",
        "label": "予定表を開く",
        "uri": f"https://liff.line.me/{LIFF_ID}/itinerary?i={LINK_ID}",
    }


async def test_a_trip_without_dates_counts_its_days(screens: ScreenCapture, tmp_path: Path) -> None:
    plan = plan_of([day_of(1, None, [item("Temple", "09:00")]), day_of(2, None, [item("Food")])])
    message = await share_of(screens, tmp_path, plan)
    assert lines_of(message)[2:] == ["1日目 09:00 Temple", "2日目 時間未定 Food"]


async def test_a_trip_that_is_over_or_empty_says_so(screens: ScreenCapture, tmp_path: Path) -> None:
    over = plan_of(
        [day_of(1, (date.today() - timedelta(days=3)).isoformat(), [item("Gone", "10:00")])]
    )
    assert lines_of(await share_of(screens, tmp_path, over)) == [
        "Kyoto trip",
        "予定はすべて終わりました。",
    ]
    assert lines_of(await share_of(screens, tmp_path, plan_of([]))) == [
        "Kyoto trip",
        "まだ予定がありません。",
    ]


async def test_without_the_share_target_picker_there_is_no_share_button(
    screens: ScreenCapture, tmp_path: Path
) -> None:
    seen = await visit(
        screens,
        itinerary_app(plan_of([day_of(1, None, [item("Temple", "09:00")])])),
        ITINERARY_ADDRESS,
        tmp_path,
        click=[SHARE],
        environment={"shareTargetPicker": False},
    )
    assert seen.shared == []
    assert seen.note is not None and "could not press '#share'" in seen.note
