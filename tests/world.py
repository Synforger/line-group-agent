"""A whole agent wired the way the service builder wires it, over a temporary folder
and a scripted API, for tests that cover answering, rolling over and the tab list."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from line_group_agent.agent.answerer import Answerer
from line_group_agent.agent.client_tool import ClientTool
from line_group_agent.agent.client_tools import ClientTools
from line_group_agent.agent.message_deleter import MessageDeleter
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.rollover import Rollover
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.events.group_watcher import GroupWatcher
from line_group_agent.media.image_store import ImageStore
from line_group_agent.media.photo_picker import PhotoPicker
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog
from line_group_agent.records.retention_sweeper import RetentionSweeper
from line_group_agent.records.summary_journal import SummaryJournal
from line_group_agent.spend.spend_books import SpendBooks
from line_group_agent.spend.spend_ledger import SpendLedger
from line_group_agent.tabs.tabs_file import TabsFile
from tests.fakes import FakeAnthropic, FakeLine, make_config

TOKYO = timezone(timedelta(hours=9))
GROUP = "Callowed"
NOW_FOR_TESTS = datetime(2026, 11, 18, 12, 0, tzinfo=TOKYO)


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
    deleter: MessageDeleter
    rollover: Rollover
    retention: RetentionSweeper
    watcher: GroupWatcher
    images: ImageStore

    def write_settings(self, **values: Any) -> None:
        self.config.settings_file.write_text(json.dumps(values), encoding="utf-8")

    def tabs_json(self) -> dict[str, Any]:
        loaded: dict[str, Any] = json.loads(self.config.tabs_file.read_text(encoding="utf-8"))
        return loaded


def build_world(
    tmp_path: Path,
    answers: list[dict[str, Any]],
    *,
    tools: Iterable[ClientTool] = (),
    **overrides: Any,
) -> World:
    config = make_config(tmp_path, **overrides)
    client_tools = ClientTools(tools)
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
    caller = ModelCaller(config, client, "SYSTEM", books, extra_tools=client_tools.definitions())
    deleter = MessageDeleter(group_log, conversations, search_limit=config.history_search_limit)
    images = ImageStore(config.state_dir)
    answerer = Answerer(
        config,
        caller,
        group_log,
        conversations,
        books,
        deleter,
        client_tools=client_tools,
        photos=PhotoPicker(images, config.max_images_per_turn),
    )
    rollover = Rollover(config, caller, journal, books, settings, clock)
    retention = RetentionSweeper(conversations, group_log, config.retention_days, clock)
    watcher = GroupWatcher(
        conversations, tabs, line, rollover, settings, clock, retention=retention
    )
    return World(
        config, client, line, clock, settings, group_log, journal, conversations, books,
        tabs, caller, answerer, deleter, rollover, retention, watcher, images,
    )  # fmt: skip
