import json
from pathlib import Path

import pytest

from line_group_agent.simulator.scenario import (
    ActionRef,
    ImageStep,
    LocationStep,
    OpenLiffStep,
    PressStep,
    TextStep,
    WaitStep,
)
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
NO_SCREENS = SimulationOptions(step_timeout_seconds=20, with_screens=False)
POLL_CALL = {
    "type": "tool_use",
    "id": "toolu_1",
    "name": "create_poll",
    "input": {"question": "Where to?", "options": ["Kyoto", "Osaka"]},
}


async def test_a_mention_is_answered_through_the_whole_bot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_scripted_model(monkeypatch, [text_answer("<reply>Hi Aki!</reply>")])
    out = tmp_path / "out"
    [transcript] = await run_simulation(
        bot_config(tmp_path),
        [scenario_of(TextStep(AKI.user_id, "hello", mention=True))],
        out,
        NO_SCREENS,
    )
    [step] = transcript.steps
    assert step.error is None
    assert step.shown == {"type": "text", "text": "@Sora hello"}
    [output] = step.outputs
    assert output.kind == "reply"
    assert output.messages[0]["text"] == "Hi Aki!"
    assert step.spend.amount > 0
    assert transcript.total_spend is not None and transcript.total_spend.usd > 0
    saved = json.loads((out / "trip" / "transcript.json").read_text(encoding="utf-8"))
    assert saved["steps"][0]["outputs"][0]["messages"][0]["text"] == "Hi Aki!"
    assert "Hi Aki!" in (out / "trip" / "chat.html").read_text(encoding="utf-8")
    assert (out / "index.html").exists()


async def test_a_message_that_calls_nobody_gets_no_reply_and_no_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_scripted_model(monkeypatch, [])
    [transcript] = await run_simulation(
        bot_config(tmp_path),
        [scenario_of(TextStep(BEN.user_id, "just chatting"))],
        tmp_path / "out",
        NO_SCREENS,
    )
    [step] = transcript.steps
    assert step.outputs == [] and step.error is None
    assert step.seconds < 5


async def test_a_poll_card_button_can_be_pressed_and_the_vote_is_counted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_scripted_model(
        monkeypatch,
        [answer([POLL_CALL], stop_reason="tool_use"), text_answer("<reply>Vote!</reply>")],
    )
    config = bot_config(tmp_path)
    [transcript] = await run_simulation(
        config,
        [
            scenario_of(
                TextStep(AKI.user_id, "poll please", mention=True),
                PressStep(BEN.user_id, ActionRef(reply_index=0, action_index=1)),
            )
        ],
        tmp_path / "out",
        NO_SCREENS,
    )
    asked, pressed = transcript.steps
    assert [message["type"] for message in asked.outputs[0].messages] == ["text", "flex"]
    assert pressed.error is None
    assert pressed.shown is not None and pressed.shown["display_text"] == "Osaka に投票"
    assert pressed.event is not None and pressed.event["type"] == "postback"
    polls = json.loads(
        (config.state_dir / "scenarios/trip/groups" / GROUP_ID / "polls.json").read_text()
    )
    [poll] = polls["polls"]
    assert [voter["user_id"] for voter in poll["options"][1]["voters"]] == [BEN.user_id]


async def test_a_photo_and_a_pin_reach_the_bot_like_line_sends_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from PIL import Image

    use_scripted_model(monkeypatch, [])
    photo = tmp_path / "menu.png"
    Image.new("RGB", (40, 30), "orange").save(photo)
    config = bot_config(tmp_path)
    [transcript] = await run_simulation(
        config,
        [
            scenario_of(
                ImageStep(AKI.user_id, photo),
                LocationStep(BEN.user_id, "Cafe", "1-2-3 Kyoto", 35.01, 135.76),
                WaitStep(0.01),
            )
        ],
        tmp_path / "out",
        NO_SCREENS,
    )
    assert [step.error for step in transcript.steps] == [None, None, None]
    log = (config.state_dir / "scenarios/trip/groups" / GROUP_ID / "messages.jsonl").read_text()
    assert "[写真]" in log and "[位置] Cafe 1-2-3 Kyoto (35.01, 135.76)" in log
    assert "Aki" in log and "Ben" in log
    assert "data:image/jpeg;base64," in (tmp_path / "out/trip/chat.html").read_text()


async def test_the_liff_card_can_be_opened_but_without_screens_it_is_only_noted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_scripted_model(
        monkeypatch,
        [answer([POLL_CALL], stop_reason="tool_use"), text_answer("<reply>Vote!</reply>")],
    )
    config = bot_config(tmp_path, liff_id=LIFF_ID, login_channel_id=LOGIN_CHANNEL_ID)
    [transcript] = await run_simulation(
        config,
        [
            scenario_of(
                TextStep(AKI.user_id, "poll please", mention=True),
                OpenLiffStep(BEN.user_id, ActionRef(reply_index=0, action_index=0)),
            )
        ],
        tmp_path / "out",
        NO_SCREENS,
    )
    opened = transcript.steps[1]
    assert opened.error is None
    assert opened.shown is not None and opened.shown["url"].startswith("https://liff.line.me/")
    assert opened.note == "screens are off: the page was not opened"


async def test_a_press_on_something_the_bot_never_sent_is_a_problem_in_the_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_scripted_model(monkeypatch, [])
    [transcript] = await run_simulation(
        bot_config(tmp_path),
        [scenario_of(PressStep(AKI.user_id, ActionRef(reply_index=3, action_index=0)))],
        tmp_path / "out",
        NO_SCREENS,
    )
    assert transcript.error_count == 1
    assert transcript.steps[0].error == "the bot has sent only 0 replies so far"


async def test_a_folder_left_by_someone_else_is_not_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from line_group_agent.simulator.simulation import SimulationError

    use_scripted_model(monkeypatch, [])
    config = bot_config(tmp_path)
    foreign = config.state_dir / "scenarios" / "trip"
    foreign.mkdir(parents=True)
    (foreign / "mine.txt").write_text("keep")
    with pytest.raises(SimulationError, match="not a simulator run folder"):
        await run_simulation(config, [scenario_of(WaitStep(0.0))], tmp_path / "out", NO_SCREENS)
    assert (foreign / "mine.txt").exists()


async def test_what_a_scenario_spends_is_added_to_the_months_figure_and_the_limit_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from line_group_agent.simulator.simulation import SimulationError

    use_scripted_model(
        monkeypatch, [text_answer("<reply>one</reply>"), text_answer("<reply>two</reply>")]
    )
    config = bot_config(tmp_path)
    first = scenario_of(TextStep(AKI.user_id, "hello", mention=True), slug="first")
    second = scenario_of(TextStep(AKI.user_id, "hello", mention=True), slug="second")
    transcripts = await run_simulation(config, [first, second], tmp_path / "out", NO_SCREENS)
    spent = [t.total_spend.amount for t in transcripts if t.total_spend]
    month = json.loads((config.state_dir / "spend.json").read_text())
    assert all(amount > 0 for amount in spent)
    assert month["spent"] == pytest.approx(sum(spent), abs=1e-3)

    from line_group_agent.spend.spend_ledger import SpendLedger

    ledger = SpendLedger(config.state_dir / "spend.json", config.budget)
    ledger.open()
    ledger.add(config.budget.monthly_limit)
    with pytest.raises(SimulationError, match="used up"):
        await run_simulation(config, [first], tmp_path / "out2", NO_SCREENS)
