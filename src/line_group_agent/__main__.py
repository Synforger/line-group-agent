"""Entry point: `line-group-agent --config <path>` starts the webhook server, and
`line-group-agent import-history …` puts an old chat history into a group's record."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from line_group_agent.config.agent_config import ConfigError, load_config
from line_group_agent.history_import.import_command import COMMAND_NAME, run_import_history
from line_group_agent.service.service_builder import build_app
from line_group_agent.spend.spend_ledger import SpendLedgerError

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def main(argv: list[str] | None = None) -> int:
    """Read the configuration and serve until stopped (or run the `import-history` command).
    Returns the exit status."""
    arguments_given = sys.argv[1:] if argv is None else argv
    if arguments_given[:1] == [COMMAND_NAME]:
        return run_import_history(arguments_given[1:])
    parser = argparse.ArgumentParser(
        prog="line-group-agent",
        description="Answer in a LINE group when the bot is mentioned.",
    )
    parser.add_argument("--config", required=True, type=Path, help="path to the JSON config")
    arguments = parser.parse_args(arguments_given)

    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    try:
        config = load_config(arguments.config)
        app = build_app(config)
    except (ConfigError, SpendLedgerError) as error:
        print(f"line-group-agent: {error}", file=sys.stderr)
        return 2
    uvicorn.run(app, host=config.host, port=config.port, log_config=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
