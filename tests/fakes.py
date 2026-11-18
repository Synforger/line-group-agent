"""Stand-ins for LINE and the Anthropic API, and a configuration builder, for tests.

No test calls a real API: these record what they were asked and answer from a script.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import anthropic
import httpx
from anthropic.types import Message

from line_group_agent.config.agent_config import AgentConfig, parse_config

PRICES_USD = {
    "input_per_mtok": 0.10,
    "output_per_mtok": 0.50,
    "cache_write_per_mtok": 0.125,
    "cache_read_per_mtok": 0.01,
    "web_search_per_thousand": 10.0,
    "long_prompt_threshold_tokens": 100000,
    "long_input_per_mtok": 0.50,
    "long_output_per_mtok": 2.50,
    "long_cache_write_per_mtok": 0.625,
    "long_cache_read_per_mtok": 0.05,
}


def raw_config(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    """Return a minimal valid configuration object whose files live under `tmp_path`."""
    raw: dict[str, Any] = {
        "allowed_group_ids": ["Callowed"],
        "persona_file": str(tmp_path / "persona.md"),
        "state_dir": str(tmp_path / "state"),
        "tab_name": "group-test",
        "anthropic_api_key_file": str(tmp_path / "anthropic-api-key"),
        "line_channel_secret_file": str(tmp_path / "line-channel-secret"),
        "line_channel_access_token_file": str(tmp_path / "line-channel-access-token"),
        "prices_usd": dict(PRICES_USD),
        "budget": {"monthly_limit": 1000, "currency": "JPY", "currency_per_usd": 150},
    }
    raw.update(overrides)
    return raw


def make_config(tmp_path: Path, **overrides: Any) -> AgentConfig:
    """Return a parsed configuration (see `raw_config`)."""
    return parse_config(raw_config(tmp_path, **overrides), tmp_path)


def text_answer(
    text: str,
    *,
    message_id: str = "msg_1",
    stop_reason: str = "end_turn",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an API answer holding one text block."""
    return answer([{"type": "text", "text": text}], message_id, stop_reason, usage)


def answer(
    content: list[dict[str, Any]],
    message_id: str = "msg_1",
    stop_reason: str = "end_turn",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return an API answer with the given content blocks."""
    return {
        "id": message_id,
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage or {"input_tokens": 1000, "output_tokens": 100},
    }


class FakeMessages:
    """Answers `create` from a script of answers and keeps every request it got."""

    def __init__(self, answers: list[dict[str, Any]] | None = None) -> None:
        self.answers = list(answers or [])
        self.requests: list[dict[str, Any]] = []
        self.error: Exception | None = None

    async def create(self, **request: Any) -> Message:
        self.requests.append(_plain(copy.deepcopy(request)))
        if self.error is not None:
            raise self.error
        if not self.answers:
            # A script that runs out stands for a request that never got an answer.
            raise anthropic.APIConnectionError(
                request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
            )
        return Message.model_validate(self.answers.pop(0))


def _plain(value: Any) -> Any:
    # Requests may hold the SDK's block objects; tests read them as plain dicts.
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


class FakeAnthropic:
    """The `client.messages` surface of the Anthropic client."""

    def __init__(self, answers: list[dict[str, Any]] | None = None) -> None:
        self.messages = FakeMessages(answers)


class FakeLine:
    """Records replies and pushes; `reply_accepts` decides each reply's outcome."""

    def __init__(self, *, reply_accepts: bool = True, names: dict[str, str] | None = None):
        self.reply_accepts = reply_accepts
        self.names = names or {}
        self.replies: list[tuple[str, str]] = []
        self.pushes: list[tuple[str, str]] = []
        self.name_lookups = 0

    async def reply(self, reply_token: str, text: str) -> bool:
        self.replies.append((reply_token, text))
        return self.reply_accepts

    async def push(self, to: str, text: str) -> None:
        self.pushes.append((to, text))

    async def get_member_name(self, group_id: str, user_id: str) -> str | None:
        self.name_lookups += 1
        return self.names.get(user_id)

    async def close(self) -> None:
        return None
