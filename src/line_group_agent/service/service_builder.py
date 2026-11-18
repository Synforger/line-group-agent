"""Put the parts together from the configuration: secrets, API clients, records,
spend, answerer, dispatcher and the web app.

Called by the entry point.
"""

from __future__ import annotations

import anthropic
import httpx2
from fastapi import FastAPI

from line_group_agent.agent.answerer import Answerer
from line_group_agent.agent.prompt import build_system
from line_group_agent.config.agent_config import AgentConfig, ConfigError, load_secrets
from line_group_agent.events.event_dispatcher import EventDispatcher
from line_group_agent.line_api.line_client import LineClient
from line_group_agent.records.conversation_log import ConversationLog
from line_group_agent.records.group_log import GroupLog
from line_group_agent.spend.spend_ledger import SpendLedger
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

    conversation_log = ConversationLog(
        config.state_dir / "conversations" / f"{config.tab_name}.jsonl"
    )
    conversation_log.open()
    ledger = SpendLedger(config.state_dir / "spend.json", config.budget)
    ledger.open()
    group_log = GroupLog(config.state_dir)

    client = create_anthropic_client(secrets.anthropic_api_key)
    line = LineClient(secrets.line_channel_access_token)
    answerer = Answerer(config, client, build_system(persona), group_log, conversation_log, ledger)
    dispatcher = EventDispatcher(
        config.allowed_group_ids,
        line,
        group_log,
        answerer,
        redelivered_answer_window_seconds=config.redelivered_answer_window_seconds,
        required_member_user_id=config.required_member_user_id,
        allow_groups_with_required_member=config.allow_groups_with_required_member,
    )
    return create_app(
        secrets.line_channel_secret,
        config.max_body_bytes,
        dispatcher,
        on_close=[line.close, client.close],
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
