"""Entry point: `python -m line_group_agent.simulator --config <bot settings> --scenario
<file or folder> --out <folder>` plays scripted chats against the bot with a stand-in LINE
and writes a transcript, a chat page and pictures for each."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from line_group_agent.config.agent_config import ConfigError, load_config
from line_group_agent.simulator.scenario_files import load_scenarios
from line_group_agent.simulator.scenario_parser import ScenarioError
from line_group_agent.simulator.simulation import (
    DEFAULT_STEP_TIMEOUT_SECONDS,
    SimulationError,
    SimulationOptions,
    run_simulation,
)
from line_group_agent.simulator.transcript import ScenarioTranscript
from line_group_agent.spend.spend_ledger import SpendLedgerError

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def main(argv: list[str] | None = None) -> int:
    """Run the scenarios; return the exit status (0 when every step was played)."""
    parser = argparse.ArgumentParser(
        prog="python -m line_group_agent.simulator",
        description="Play scripted chats against the bot with a stand-in LINE.",
    )
    parser.add_argument("--config", required=True, type=Path, help="the bot settings to try")
    parser.add_argument(
        "--scenario", required=True, type=Path, help="a scenario JSON file or a folder of them"
    )
    parser.add_argument("--out", required=True, type=Path, help="where the results go")
    parser.add_argument(
        "--step-timeout",
        type=float,
        default=DEFAULT_STEP_TIMEOUT_SECONDS,
        help="seconds to wait for the bot on one step (default %(default)s)",
    )
    parser.add_argument(
        "--max-usd", type=float, default=None, help="stop a scenario once it has spent this much"
    )
    parser.add_argument("--no-screens", action="store_true", help="skip the pictures")
    arguments = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)
    try:
        config = load_config(arguments.config)
        scenarios = load_scenarios(arguments.scenario)
        transcripts = asyncio.run(
            run_simulation(
                config,
                scenarios,
                arguments.out,
                SimulationOptions(
                    step_timeout_seconds=arguments.step_timeout,
                    max_usd=arguments.max_usd,
                    with_screens=not arguments.no_screens,
                ),
                on_done=_report,
            )
        )
    except (ConfigError, ScenarioError, SimulationError, SpendLedgerError) as error:
        print(f"simulator: {error}", file=sys.stderr)
        return 2
    print(f"simulator: wrote {arguments.out / 'index.html'}")
    return 1 if any(transcript.error_count for transcript in transcripts) else 0


def _report(transcript: ScenarioTranscript) -> None:
    spend = transcript.total_spend
    cost = f"${spend.usd:.4f}" if spend else "-"
    print(
        f"simulator: {transcript.slug}: {len(transcript.steps)} steps, "
        f"{transcript.total_seconds:.1f}s, {cost}, {transcript.error_count} problems"
    )


if __name__ == "__main__":
    sys.exit(main())
