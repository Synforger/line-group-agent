"""Put the parts together from the configuration: secrets, API clients, records,
spend, answerer, rollover, group watcher, dispatcher and the web app.

Called by the entry point.
"""

from __future__ import annotations

from datetime import datetime

import anthropic
import httpx2
from fastapi import FastAPI

from line_group_agent.agent.answerer import Answerer
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import build_system
from line_group_agent.agent.rollover import Rollover
from line_group_agent.config.agent_config import AgentConfig, ConfigError, load_secrets
from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.events.group_watcher import GroupWatcher
from line_group_agent.line_api.line_client import LineClient
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog
from line_group_agent.records.summary_journal import SummaryJournal
from line_group_agent.service.patrol import Patrol
from line_group_agent.spend.spend_books import SpendBooks
from line_group_agent.spend.spend_ledger import SpendLedger
from line_group_agent.tabs.tabs_file import TabsFile
from line_group_agent.webhook.webhook_app import create_app

ANTHROPIC_BASE_URL = "https://api.anthropic.com"
ANTHROPIC_TIMEOUT_SECONDS = 300.0


def build_app(config: AgentConfig) -> FastAPI:
    """Read the secrets and the persona, open the records, and return the web app."""
    secrets = load_secrets(config)
    try:
        persona = config.persona_file.read_text(encoding="utf-8")
    except OSError as error:
        raise ConfigError(f"cannot read persona_file: {error.strerror}") from error

    def clock() -> datetime:
        return datetime.now().astimezone()

    settings = SettingsStore(config.settings_file)
    group_log = GroupLog(config.state_dir)
    journal = SummaryJournal(config.state_dir)
    conversations = GroupConversations(config.state_dir, group_log, journal)
    conversations.open(config.allowed_group_ids)
    overall = SpendLedger(config.state_dir / "spend.json", config.budget)
    overall.open()
    books = SpendBooks(overall, config.state_dir, config.budget, settings, conversations.count)
    tabs = TabsFile(config.tabs_file, conversations, books, settings, clock)

    client = create_anthropic_client(secrets.anthropic_api_key)
    line = LineClient(secrets.line_channel_access_token)
    caller = ModelCaller(config, client, build_system(persona), books)
    answerer = Answerer(config, caller, group_log, conversations, books)
    rollover = Rollover(config, caller, journal, books, settings, clock)
    watcher = GroupWatcher(conversations, tabs, line, rollover, settings, clock)
    tabs.refresh()
    dispatcher = EventDispatcher(
        config.allowed_group_ids,
        line,
        group_log,
        answerer,
        redelivered_answer_window_seconds=config.redelivered_answer_window_seconds,
        required_member_user_id=config.required_member_user_id,
        allow_groups_with_required_member=config.allow_groups_with_required_member,
        observer=watcher,
    )
    return create_app(
        secrets.line_channel_secret,
        config.max_body_bytes,
        dispatcher,
        on_close=[line.close, client.close],
        background=[Patrol(watcher.patrol, config.patrol_interval_seconds)],
    )


def create_anthropic_client(api_key: str) -> anthropic.AsyncAnthropic:
    """Return an API client that takes nothing from environment variables.

    The key, the address and tracing are given explicitly, and the HTTP client is a
    plain one with `trust_env=False`: the SDK's default HTTP client adds proxies from
    the environment even when told not to trust it.
    """
    http_client = httpx2.AsyncClient(timeout=ANTHROPIC_TIMEOUT_SECONDS, trust_env=False)
    return anthropic.AsyncAnthropic(
        api_key=api_key,
        base_url=ANTHROPIC_BASE_URL,
        open_telemetry=False,
        http_client=http_client,
    )
