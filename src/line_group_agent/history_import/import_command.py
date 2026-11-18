"""The command `line-group-agent import-history --config <path> --group <groupId> <file>`.

Reads LINE's "send chat history" text file and puts its messages into the group's record
(see the history importer). Run it while the agent is stopped: the record is replaced whole,
so a message the agent wrote at the same moment would be lost. Called by the entry point.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from line_group_agent.config.agent_config import ConfigError, load_config
from line_group_agent.history_import.history_importer import HistoryImporter
from line_group_agent.records.group_log import GROUP_ID_PATTERN, GroupLog

COMMAND_NAME = "import-history"


def run_import_history(argv: list[str]) -> int:
    """Run the command and return its exit status (0 done, 2 a mistake in the arguments,
    the configuration or the file)."""
    parser = argparse.ArgumentParser(
        prog=f"line-group-agent {COMMAND_NAME}",
        description="Put the messages of an old LINE chat history file into a group's record.",
    )
    parser.add_argument("--config", required=True, type=Path, help="path to the JSON config")
    parser.add_argument("--group", required=True, help="the group's id")
    parser.add_argument("file", type=Path, help='the .txt file LINE makes with "send chat history"')
    arguments = parser.parse_args(argv)
    if not GROUP_ID_PATTERN.match(arguments.group):
        return _fail("the group id holds only letters and digits")
    try:
        config = load_config(arguments.config)
        text = arguments.file.read_text(encoding="utf-8-sig", errors="replace")
    except (ConfigError, OSError) as error:
        return _fail(str(error))
    result = HistoryImporter(GroupLog(config.state_dir)).import_text(arguments.group, text)
    print(
        f"added {result.added_count} message(s); {result.existing_count} already in the record; "
        f"{result.notice_count} notice line(s) skipped; "
        f"{result.unrecognized_count} line(s) not understood"
    )
    return 0


def _fail(message: str) -> int:
    print(f"line-group-agent {COMMAND_NAME}: {message}", file=sys.stderr)
    return 2
