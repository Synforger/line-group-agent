"""A whole agent wired the way the service builder wires it, over a temporary folder
and a scripted API, for tests that cover answering, rolling over and the tab list."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from line_group_agent.agent.answerer import Answerer
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.rollover import Rollover
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.events.group_watcher import GroupWatcher
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog
from line_group_agent.records.summary_journal import SummaryJournal
from line_group_agent.spend.spend_books import SpendBooks
from line_group_agent.spend.spend_ledger import SpendLedger
from line_group_agent.tabs.tabs_file import TabsFile
from tests.fakes import FakeAnthropic, FakeLine, make_config

TOKYO = timezone(timedelta(hours=9))
GROUP = "Callowed"


class Clock:
    """A clock the test moves by hand."""

    def __init__(self, moment: datetime | None = None) -> None:
        self.moment = moment or datetime(2026, 11, 18, 12, 0, tzinfo=TOKYO)

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta: float) -> None:
        self.moment += timedelta(**delta)


@dataclass
class World:
    config: AgentConfig
    client: FakeAnthropic
    line: FakeLine
    clock: Clock
    settings: SettingsStore
    group_log: GroupLog
    journal: SummaryJournal
    conversations: GroupConversations
    books: SpendBooks
    tabs: TabsFile
    caller: ModelCaller
    answerer: Answerer
    rollover: Rollover
    watcher: GroupWatcher

    def write_settings(self, **values: Any) -> None:
        self.config.settings_file.write_text(json.dumps(values), encoding="utf-8")

    def tabs_json(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.config.tabs_file.read_text(encoding="utf-8"))
        return loaded


def build_world(tmp_path: Path, answers: list[dict[str, Any]], **overrides: Any) -> World:
    config = make_config(tmp_path, **overrides)
    client = FakeAnthropic(answers)
    line = FakeLine(group_names={GROUP: "Trip friends"})
    clock = Clock()
    settings = SettingsStore(config.settings_file)
    group_log = GroupLog(config.state_dir)
    journal = SummaryJournal(config.state_dir)
    conversations = GroupConversations(config.state_dir, group_log, journal)
    conversations.open(config.allowed_group_ids)
    overall = SpendLedger(config.state_dir / "spend.json", config.budget)
    overall.open()
    books = SpendBooks(overall, config.state_dir, config.budget, settings, conversations.count)
    tabs = TabsFile(config.tabs_file, conversations, books, settings, clock)
    caller = ModelCaller(config, client, "SYSTEM", books)
    answerer = Answerer(config, caller, group_log, conversations, books)
    rollover = Rollover(config, caller, journal, books, settings, clock)
    watcher = GroupWatcher(conversations, tabs, line, rollover, settings, clock)
    return World(
        config, client, line, clock, settings, group_log, journal, conversations, books,
        tabs, caller, answerer, rollover, watcher,
    )  # fmt: skip
