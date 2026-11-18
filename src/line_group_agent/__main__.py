"""Entry point: `line-group-agent --config <path>` starts the webhook server."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import uvicorn

from line_group_agent.config.agent_config import ConfigError, load_config
from line_group_agent.service.service_builder import build_app
from line_group_agent.spend.spend_ledger import SpendLedgerError

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def main(argv: list[str] | None = None) -> int:
    """Read the configuration and serve until stopped. Returns the exit status."""
    parser = argparse.ArgumentParser(
        prog="line-group-agent",
        description="Answer in a LINE group when the bot is mentioned.",
    )
    parser.add_argument("--config", required=True, type=Path, help="path to the JSON config")
    arguments = parser.parse_args(argv)

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
