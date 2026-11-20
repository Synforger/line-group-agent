"""Run scenarios against the real bot with a stand-in LINE: for each scenario start the
stand-in LINE server and the bot (the same build as production, a fresh state folder, other
ports, the LINE addresses pointed at the stand-in), play the steps, close both, and write the
transcript, the chat page and the pictures.

Each scenario runs in its own state folder, so it starts from an empty group; what it spent
is added to the month's figure in `<state_dir>/spend.json`, and the next scenario may spend
only what is left of the month's limit.

Called by the simulator's entry point.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI

from line_group_agent.config.agent_config import AgentConfig, load_secrets
from line_group_agent.service.service_builder import build_app
from line_group_agent.simulator.fake_line_server import FakeLineServer
from line_group_agent.simulator.local_server import LocalServer
from line_group_agent.simulator.report_writer import write_index, write_scenario_report
from line_group_agent.simulator.scenario import Scenario
from line_group_agent.simulator.scenario_clock import ScenarioClock
from line_group_agent.simulator.scenario_runner import ScenarioRunner
from line_group_agent.simulator.screen_capture import ScreenCapture, ScreensUnavailableError
from line_group_agent.simulator.transcript import ScenarioTranscript
from line_group_agent.spend.spend_ledger import SpendLedger

RUNS_FOLDER = "scenarios"
RUN_MARKER = ".simulator-run"
SCREENS_FOLDER = "screens"
CHAT_PICTURE = "chat.png"
DEFAULT_STEP_TIMEOUT_SECONDS = 180.0


class SimulationError(RuntimeError):
    """The run could not be set up."""


@dataclass(frozen=True)
class SimulationOptions:
    """How a run goes: how long to wait for the bot on one step, the spend (in US dollars)
    after which a scenario is stopped, and whether to take pictures."""

    step_timeout_seconds: float = DEFAULT_STEP_TIMEOUT_SECONDS
    max_usd: float | None = None
    with_screens: bool = True


BotBuilder = Callable[[AgentConfig, Callable[[], datetime]], FastAPI]


async def run_simulation(
    config: AgentConfig,
    scenarios: Sequence[Scenario],
    out_dir: Path,
    options: SimulationOptions,
    *,
    build_bot: BotBuilder = build_app,
    on_done: Callable[[ScenarioTranscript], None] | None = None,
) -> list[ScenarioTranscript]:
    """Play every scenario and write the pages under `out_dir`; return the transcripts."""
    screens = await _open_screens(options)
    transcripts: list[ScenarioTranscript] = []
    try:
        for scenario in scenarios:
            transcript = await _run_scenario(config, scenario, out_dir, options, screens, build_bot)
            transcripts.append(transcript)
            if on_done is not None:
                on_done(transcript)
    finally:
        if screens is not None:
            await screens.close()
    write_index(out_dir, transcripts)
    return transcripts


async def _open_screens(options: SimulationOptions) -> ScreenCapture | None:
    if not options.with_screens:
        return None
    screens = ScreenCapture()
    try:
        await screens.open()
    except ScreensUnavailableError as error:
        print(f"simulator: no pictures this time ({error})")
        return None
    return screens


async def _run_scenario(
    config: AgentConfig,
    scenario: Scenario,
    out_dir: Path,
    options: SimulationOptions,
    screens: ScreenCapture | None,
    build_bot: BotBuilder,
) -> ScenarioTranscript:
    scenario_dir = out_dir / scenario.slug
    screens_dir = scenario_dir / SCREENS_FOLDER
    month = SpendLedger(config.state_dir / "spend.json", config.budget)
    month.open()
    if month.spent >= month.limit:
        raise SimulationError("this month's budget for the simulator is used up")
    run_dir = _prepare_run_dir(config.state_dir, scenario.slug)
    line = FakeLineServer(scenario.group)
    line_server = LocalServer(line.app)
    await line_server.start()
    try:
        bot_config = replace(
            config,
            allowed_group_ids=frozenset({scenario.group.id}),
            state_dir=run_dir,
            tabs_file=run_dir / "tabs.json",
            budget=replace(config.budget, monthly_limit=month.limit - month.spent),
            line_api_base_url=line_server.base_url,
            line_data_api_base_url=line_server.base_url,
        )
        clock = ScenarioClock()
        app = build_bot(bot_config, clock)
        bot_server = LocalServer(app)
        await bot_server.start()
        try:
            runner = ScenarioRunner(
                scenario,
                line=line,
                bot_url=bot_server.base_url,
                channel_secret=load_secrets(bot_config).line_channel_secret,
                event_sink=app.state.event_sink,
                clock=clock,
                run_reminder_round=app.state.run_reminder_round,
                state_dir=run_dir,
                currency=config.budget.currency,
                currency_per_usd=config.budget.currency_per_usd,
                screens=screens,
                screens_dir=screens_dir,
                step_timeout_seconds=options.step_timeout_seconds,
                max_usd=options.max_usd,
            )
            transcript = await runner.run()
        finally:
            await bot_server.stop()
    finally:
        await line_server.stop()
    if transcript.total_spend is not None:
        month.add(transcript.total_spend.amount)
    chat_file = write_scenario_report(scenario_dir, transcript)
    if screens is not None:
        screens_dir.mkdir(parents=True, exist_ok=True)
        await screens.capture_chat(chat_file, screens_dir / CHAT_PICTURE)
    return transcript


def _prepare_run_dir(state_root: Path, slug: str) -> Path:
    """Return an empty state folder for this scenario under `state_root`. A folder left by an
    earlier run is cleared only when it carries this tool's marker."""
    run_dir = state_root / RUNS_FOLDER / slug
    if run_dir.exists():
        if not (run_dir / RUN_MARKER).exists():
            raise SimulationError(f"{run_dir} exists and is not a simulator run folder")
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    (run_dir / RUN_MARKER).write_text("made by the simulator\n", encoding="utf-8")
    return run_dir
