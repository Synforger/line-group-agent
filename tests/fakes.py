"""Stand-ins for LINE and the Anthropic API, and a configuration builder, for tests.

No test calls a real API: these record what they were asked and answer from a script.
"""

from __future__ import annotations

import copy
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
import httpx
from anthropic.types import Message

from line_group_agent.cards.card import Card
from line_group_agent.config.agent_config import AgentConfig, parse_config
from line_group_agent.line_api.line_client import LineApiError, ReplyResult
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem

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


@dataclass
class SentCall:
    """One reply or push that reached the fake."""

    kind: str
    target: str
    text: str | None
    cards: list[Card]
    with_images: bool
    quote_token: str | None = None
    extras: list[OutgoingExtra] | None = None
    quick_replies: list[QuickReplyItem] | None = None


class FakeLine:
    """Records replies and pushes.

    `reply_accepts` decides each reply's outcome; `reply_results` scripts the
    outcomes in order instead, and `push_statuses` scripts each push's failure status
    (None lets the push through). `remaining_messages` is what the quota question
    answers, and `quota_lookups` counts the questions.
    """

    def __init__(
        self,
        *,
        reply_accepts: bool = True,
        names: dict[str, str] | None = None,
        reply_results: list[ReplyResult] | None = None,
        push_statuses: list[int | None] | None = None,
        members: dict[str, bool | None] | None = None,
        group_names: dict[str, str] | None = None,
        remaining_messages: int | None = 1000,
        contents: dict[str, tuple[bytes, str]] | None = None,
    ) -> None:
        self.contents = contents or {}
        self.content_lookups: list[str] = []
        self.remaining_messages = remaining_messages
        self.quota_lookups = 0
        self.members = members or {}
        self.group_names = group_names or {}
        self.group_name_lookups = 0
        self.left_groups: list[str] = []
        self.reply_accepts = reply_accepts
        self.names = names or {}
        self.reply_results = list(reply_results or [])
        self.push_statuses = list(push_statuses or [])
        self.calls: list[SentCall] = []
        self.name_lookups = 0

    @property
    def replies(self) -> list[tuple[str, str | None]]:
        return [(c.target, c.text) for c in self.calls if c.kind == "reply"]

    @property
    def pushes(self) -> list[tuple[str, str | None]]:
        return [(c.target, c.text) for c in self.calls if c.kind == "push"]

    async def reply(
        self,
        reply_token: str,
        text: str | None,
        cards: Sequence[Card] = (),
        *,
        with_images: bool = True,
        quote_token: str | None = None,
        extras: Sequence[OutgoingExtra] = (),
        quick_replies: Sequence[QuickReplyItem] = (),
    ) -> ReplyResult:
        self.calls.append(
            SentCall(
                "reply",
                reply_token,
                text,
                list(cards),
                with_images,
                quote_token,
                list(extras),
                list(quick_replies),
            )  # fmt: skip
        )
        if self.reply_results:
            return self.reply_results.pop(0)
        return ReplyResult.SENT if self.reply_accepts else ReplyResult.TOKEN_REFUSED

    async def push(
        self,
        to: str,
        text: str | None,
        cards: Sequence[Card] = (),
        *,
        with_images: bool = True,
        quote_token: str | None = None,
        extras: Sequence[OutgoingExtra] = (),
        quick_replies: Sequence[QuickReplyItem] = (),
    ) -> None:
        self.calls.append(
            SentCall(
                "push",
                to,
                text,
                list(cards),
                with_images,
                quote_token,
                list(extras),
                list(quick_replies),
            )  # fmt: skip
        )
        status = self.push_statuses.pop(0) if self.push_statuses else None
        if status is not None:
            raise LineApiError("push", status)

    async def get_member_name(self, group_id: str, user_id: str) -> str | None:
        self.name_lookups += 1
        return self.names.get(user_id)

    async def get_message_content(self, message_id: str) -> tuple[bytes, str] | None:
        self.content_lookups.append(message_id)
        return self.contents.get(message_id)

    async def get_group_name(self, group_id: str) -> str | None:
        self.group_name_lookups += 1
        return self.group_names.get(group_id)

    async def is_member(self, group_id: str, user_id: str) -> bool | None:
        return self.members.get(user_id, False)

    async def leave_group(self, group_id: str) -> None:
        self.left_groups.append(group_id)

    async def get_remaining_messages(self) -> int | None:
        self.quota_lookups += 1
        return self.remaining_messages

    async def close(self) -> None:
        return None
