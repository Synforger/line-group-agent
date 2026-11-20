"""A member's use of a LIFF page inside a scripted chat: what the page sends in the member's
name reaches the bot like any message of theirs, and what it shares is kept in the record."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.simulator import simulation
from line_group_agent.simulator.scenario import ActionRef, LiffClickStep, TextStep
from line_group_agent.simulator.screen_capture import LiffVisit
from line_group_agent.simulator.simulation import SimulationOptions, run_simulation
from tests.fakes import answer, text_answer
from tests.simulator.harness import (
    AKI,
    BEN,
    GROUP_ID,
    LIFF_ID,
    LOGIN_CHANNEL_ID,
    bot_config,
    scenario_of,
    use_scripted_model,
)

pytestmark = pytest.mark.anyio
OPEN_THE_POLL = ActionRef(reply_index=0, action_index=0)
SECOND_OPTION = "#options li:nth-child(2) button"
SHARE = "#share"
POLL_CALL = {
    "type": "tool_use",
    "id": "toolu_1",
    "name": "create_poll",
    "input": {"question": "Where to?", "options": ["Kyoto", "Osaka"]},
}


def poll_then_click(selector: str) -> Any:
    return scenario_of(
        TextStep(AKI.user_id, "poll please", mention=True),
        LiffClickStep(BEN.user_id, OPEN_THE_POLL, selector),
    )


def scripted_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    use_scripted_model(
        monkeypatch,
        [answer([POLL_CALL], stop_reason="tool_use"), text_answer("<reply>Vote!</reply>")],
    )


class FakeScreens:
    """Stands in for the browser: opening a page gives back what `visit` says it left."""

    def __init__(self, visit: LiffVisit) -> None:
        self.visit = visit
        self.opened: list[tuple[str, tuple[str, ...]]] = []

    async def open(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def capture_chat(self, page_file: Path, png_file: Path) -> None:
        return None

    async def capture_liff(
        self, page_url: str, id_token: str, png_file: Path, *, click: tuple[str, ...] = ()
    ) -> LiffVisit:
        self.opened.append((page_url, tuple(click)))
        return self.visit


async def test_what_the_page_sends_for_the_member_reaches_the_bot_who_does_not_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted_poll(monkeypatch)
    fake = FakeScreens(LiffVisit(None, sent=[{"type": "text", "text": "Osaka に入れたよ"}]))
    monkeypatch.setattr(simulation, "ScreenCapture", lambda: fake)
    config = bot_config(tmp_path, liff_id=LIFF_ID, login_channel_id=LOGIN_CHANNEL_ID)
    [transcript] = await run_simulation(
        config,
        [poll_then_click(SECOND_OPTION)],
        tmp_path / "out",
        SimulationOptions(step_timeout_seconds=20),
    )
    clicked = transcript.steps[1]
    assert clicked.error is None and clicked.kind == "liff_click"
    assert clicked.shown is not None and clicked.shown["selector"] == SECOND_OPTION
    assert clicked.liff_sent == [{"type": "text", "text": "Osaka に入れたよ"}]
    assert clicked.event is not None
    assert clicked.event["source"]["userId"] == BEN.user_id
    assert clicked.event["message"]["text"] == "Osaka に入れたよ"
    assert clicked.outputs == [] and clicked.spend.amount == 0
    [(page_url, click)] = fake.opened
    assert "/liff/?p=" in page_url and click == (SECOND_OPTION,)
    log = (config.state_dir / "scenarios/trip/groups" / GROUP_ID / "messages.jsonl").read_text()
    assert "Osaka に入れたよ" in log
    chat = (tmp_path / "out/trip/chat.html").read_text(encoding="utf-8")
    assert "Osaka に入れたよ" in chat and "Ben" in chat


async def test_what_the_page_shares_is_kept_and_drawn_but_sends_nothing_to_the_bot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted_poll(monkeypatch)
    card = {
        "type": "flex",
        "altText": "投票: Where to?",
        "contents": {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [{"type": "text", "text": "Where to?"}],
            },
        },
    }
    shared = {"messages": [card], "options": {"isMultiple": True}}
    monkeypatch.setattr(
        simulation, "ScreenCapture", lambda: FakeScreens(LiffVisit(None, [], [shared]))
    )
    config = bot_config(tmp_path, liff_id=LIFF_ID, login_channel_id=LOGIN_CHANNEL_ID)
    [transcript] = await run_simulation(
        config,
        [poll_then_click(SHARE)],
        tmp_path / "out",
        SimulationOptions(step_timeout_seconds=20),
    )
    clicked = transcript.steps[1]
    assert clicked.liff_shared == [shared] and clicked.event is None and clicked.outputs == []
    saved = json.loads((tmp_path / "out/trip/transcript.json").read_text(encoding="utf-8"))
    assert saved["steps"][1]["liff_shared"][0]["messages"][0]["altText"] == "投票: Where to?"
    chat = (tmp_path / "out/trip/chat.html").read_text(encoding="utf-8")
    assert "Where to?" in chat and "share target picker" in chat


async def test_without_screens_the_click_is_only_noted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted_poll(monkeypatch)
    config = bot_config(tmp_path, liff_id=LIFF_ID, login_channel_id=LOGIN_CHANNEL_ID)
    [transcript] = await run_simulation(
        config,
        [poll_then_click(SECOND_OPTION)],
        tmp_path / "out",
        SimulationOptions(step_timeout_seconds=20, with_screens=False),
    )
    clicked = transcript.steps[1]
    assert clicked.error is None and clicked.liff_sent == []
    assert clicked.note == "screens are off: the page was not opened"


async def test_a_vote_on_the_real_page_is_counted_and_its_one_liner_is_not_answered(
    screens: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scripted_poll(monkeypatch)
    config = bot_config(tmp_path, liff_id=LIFF_ID, login_channel_id=LOGIN_CHANNEL_ID)
    [transcript] = await run_simulation(
        config,
        [poll_then_click(SECOND_OPTION)],
        tmp_path / "out",
        SimulationOptions(step_timeout_seconds=20),
    )
    clicked = transcript.steps[1]
    assert clicked.error is None and clicked.note is None
    assert clicked.liff_sent == [{"type": "text", "text": "Osaka に入れたよ"}]
    assert clicked.outputs == [] and clicked.spend.amount == 0
    polls = json.loads(
        (config.state_dir / "scenarios/trip/groups" / GROUP_ID / "polls.json").read_text()
    )
    [poll] = polls["polls"]
    assert [voter["user_id"] for voter in poll["options"][1]["voters"]] == [BEN.user_id]
    assert (tmp_path / "out/trip/screens/step-01-liff.png").exists()
