"""A bot configuration and a scripted model for the simulator's tests: the bot is the real
build, the Anthropic API is the fake of `tests/fakes.py`, and LINE is the simulator's own."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.service import service_builder
from line_group_agent.simulator.scenario import Group, Member, Scenario, Step
from tests.fakes import FakeAnthropic, make_config

GROUP_ID = "Csimgroup"
LIFF_ID = "1234567890-AbCdEfGh"
LOGIN_CHANNEL_ID = "1234567890"
AKI = Member("Uaki", "Aki")
BEN = Member("Uben", "Ben")


class ScriptedAnthropic(FakeAnthropic):
    """The fake Anthropic client with the `close` the service builder calls."""

    async def close(self) -> None:
        return None


def use_scripted_model(monkeypatch: pytest.MonkeyPatch, answers: list[dict[str, Any]]) -> None:
    """Make the service builder give the bot a model that answers from `answers`."""
    client = ScriptedAnthropic(answers)
    monkeypatch.setattr(service_builder, "create_anthropic_client", lambda _key: client)


def bot_config(tmp_path: Path, **overrides: Any) -> AgentConfig:
    """Return a bot configuration whose persona and secret files exist under `tmp_path`."""
    config = make_config(tmp_path / "bot", **overrides)
    config.persona_file.parent.mkdir(parents=True, exist_ok=True)
    config.persona_file.write_text("You are a helper.", encoding="utf-8")
    for secret_file in (
        config.anthropic_api_key_file,
        config.line_channel_secret_file,
        config.line_channel_access_token_file,
    ):
        secret_file.write_text("secret\n", encoding="utf-8")
    return config


def scenario_of(*steps: Step, slug: str = "trip", bot_name: str = "Sora") -> Scenario:
    """Return a scenario of a group with Aki and Ben."""
    group = Group(GROUP_ID, "Trip friends", (AKI, BEN))
    return Scenario(slug=slug, name="A trip", group=group, steps=steps, bot_name=bot_name)
