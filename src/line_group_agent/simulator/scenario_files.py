"""Find and read scenario files: one JSON file is one scenario, a folder holds many.

Reads files; called by the simulator's entry point.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from line_group_agent.simulator.scenario import Scenario
from line_group_agent.simulator.scenario_parser import ScenarioError, parse_scenario

SCENARIO_SUFFIX = ".json"
SLUG_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def load_scenarios(path: Path) -> list[Scenario]:
    """Read the scenario in `path`, or every `*.json` directly inside it (by file name)."""
    if path.is_dir():
        files = sorted(
            file
            for file in path.iterdir()
            if file.suffix == SCENARIO_SUFFIX and not file.name.startswith(".")
        )
        if not files:
            raise ScenarioError(f"no scenario files in {path}")
    elif path.is_file():
        files = [path]
    else:
        raise ScenarioError(f"cannot find the scenario {path}")
    scenarios = [_load(file) for file in files]
    slugs = [scenario.slug for scenario in scenarios]
    if len(set(slugs)) != len(slugs):
        raise ScenarioError("two scenario files make the same folder name")
    return scenarios


def _load(file: Path) -> Scenario:
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ScenarioError(f"cannot read the scenario file {file}: {error}") from error
    slug = SLUG_UNSAFE.sub("-", file.stem).strip("-") or "scenario"
    try:
        return parse_scenario(raw, file.resolve().parent, slug)
    except ScenarioError as error:
        raise ScenarioError(f"{file.name}: {error}") from error
