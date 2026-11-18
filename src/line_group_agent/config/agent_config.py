"""Settings of the agent, read once at start from one JSON file (`--config <path>`).

Called by the entry point. Secrets are not kept in the JSON: it names the files that
hold them, and `load_secrets` reads those files. Prices and the monthly limit have no
defaults on purpose: they are money decisions the operator writes down.

No setting comes from environment variables or from the working directory: a relative
path in the file is taken from the folder that holds the configuration file.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8790
DEFAULT_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_MAX_TOKENS = 1024
DEFAULT_EFFORT = "low"
DEFAULT_RECENT_MESSAGE_COUNT = 30
DEFAULT_MAX_TOOL_ROUNDS = 4
DEFAULT_HISTORY_SEARCH_LIMIT = 20
DEFAULT_REDELIVERED_ANSWER_WINDOW_SECONDS = 600
DEFAULT_HELP_KEYWORDS = ("help",)
DEFAULT_ITINERARY_KEYWORDS = ("itinerary",)
DEFAULT_WEB_SEARCH_TYPE = "web_search_20250305"
DEFAULT_WEB_SEARCH_MAX_USES = 3
DEFAULT_WEB_FETCH_TYPE = "web_fetch_20250910"
DEFAULT_WEB_FETCH_MAX_USES = 2
DEFAULT_WEB_FETCH_MAX_CONTENT_TOKENS = 8000
DEFAULT_CACHE_TTL = "1h"
CACHE_TTLS = ("5m", "1h")
DEFAULT_SUMMARY_MAX_TOKENS = 2048
DEFAULT_MAX_CATCH_UP_MESSAGES = 200
DEFAULT_PATROL_INTERVAL_SECONDS = 600
DEFAULT_SETTINGS_FILE_NAME = "settings.json"
DEFAULT_TABS_FILE_NAME = "tabs.json"
DEFAULT_CURRENCY = "JPY"
DEFAULT_ESTIMATED_INPUT_TOKENS = 20000
DEFAULT_EXHAUSTED_TEXT = "This month's budget is used up."
DEFAULT_ERROR_TEXT = "Something went wrong, so I could not answer. Please try again in a bit."
DEFAULT_WAIT_TEXT = "Looking that up, one moment."
DEFAULT_WAIT_MIN_PUSH_LEFT = 20
DEFAULT_MAX_MENTIONS_PER_USER_PER_HOUR = 20
DEFAULT_RATE_LIMIT_TEXT = "You have asked a lot in the last hour. Please try again a little later."
DEFAULT_RETENTION_DAYS = 30


class ConfigError(ValueError):
    """The configuration file is missing a value or holds one of the wrong kind."""


@dataclass(frozen=True)
class PriceConfig:
    """Prices of the model in US dollars, from the provider's pricing page."""

    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float
    cache_read_per_mtok: float
    web_search_per_thousand: float
    cache_write_1h_per_mtok: float | None
    long_cache_write_1h_per_mtok: float | None
    long_prompt_threshold_tokens: int | None
    long_input_per_mtok: float | None
    long_output_per_mtok: float | None
    long_cache_write_per_mtok: float | None
    long_cache_read_per_mtok: float | None


@dataclass(frozen=True)
class BudgetConfig:
    """The monthly limit and how a dollar figure becomes the reported currency."""

    monthly_limit: float
    currency: str
    currency_per_usd: float
    estimated_input_tokens_per_request: int
    exhausted_text: str


@dataclass(frozen=True)
class WebToolConfig:
    """One server-side web tool (search or fetch); `None` in its place turns it off."""

    type: str
    max_uses: int
    max_content_tokens: int | None


@dataclass(frozen=True)
class Secrets:
    """The three secrets, read from their files at start. Never logged."""

    anthropic_api_key: str
    line_channel_secret: str
    line_channel_access_token: str


@dataclass(frozen=True)
class AgentConfig:
    """Everything the agent reads from its configuration file."""

    host: str
    port: int
    max_body_bytes: int
    allowed_group_ids: frozenset[str]
    persona_file: Path
    state_dir: Path
    settings_file: Path
    tabs_file: Path
    anthropic_api_key_file: Path
    line_channel_secret_file: Path
    line_channel_access_token_file: Path
    model: str
    max_tokens: int
    effort: str
    cache_ttl: str
    recent_message_count: int
    max_catch_up_messages: int
    summary_max_tokens: int
    patrol_interval_seconds: int
    max_tool_rounds: int
    history_search_limit: int
    redelivered_answer_window_seconds: int
    required_member_user_id: str | None
    allow_groups_with_required_member: bool
    alert_user_id: str | None
    intro_file: Path | None
    help_file: Path | None
    help_keywords: tuple[str, ...]
    itinerary_keywords: tuple[str, ...]
    call_names: tuple[str, ...]
    error_text: str
    wait_text: str
    wait_min_push_left: int
    max_mentions_per_user_per_hour: int
    rate_limit_text: str
    retention_days: int
    web_search: WebToolConfig | None
    web_fetch: WebToolConfig | None
    prices: PriceConfig
    budget: BudgetConfig


def load_config(path: Path) -> AgentConfig:
    """Read and check the configuration file at `path`."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read the configuration file {path}: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError("the configuration file must hold one JSON object")
    return parse_config(raw, path.resolve().parent)


def parse_config(raw: dict[str, Any], base_dir: Path) -> AgentConfig:
    """Build the configuration from an already-parsed JSON object; relative paths are
    taken from `base_dir` (the configuration file's folder)."""

    def path_of(key: str) -> Path:
        return base_dir / Path(_required(raw, key, str))

    cache_ttl = _optional(raw, "cache_ttl", str, DEFAULT_CACHE_TTL)
    if cache_ttl not in CACHE_TTLS:
        raise ConfigError("cache_ttl must be '5m' or '1h'")
    state_dir = path_of("state_dir")
    group_ids = _optional(raw, "allowed_group_ids", list, [])
    if not all(isinstance(group_id, str) for group_id in group_ids):
        raise ConfigError("allowed_group_ids must be a list of strings")
    return AgentConfig(
        host=_optional(raw, "host", str, DEFAULT_HOST),
        port=_optional(raw, "port", int, DEFAULT_PORT),
        max_body_bytes=_optional(raw, "max_body_bytes", int, DEFAULT_MAX_BODY_BYTES),
        allowed_group_ids=frozenset(group_ids),
        persona_file=path_of("persona_file"),
        state_dir=state_dir,
        settings_file=_optional_path(
            raw, "settings_file", base_dir, base_dir / DEFAULT_SETTINGS_FILE_NAME
        ),
        tabs_file=_optional_path(raw, "tabs_file", base_dir, state_dir / DEFAULT_TABS_FILE_NAME),
        anthropic_api_key_file=path_of("anthropic_api_key_file"),
        line_channel_secret_file=path_of("line_channel_secret_file"),
        line_channel_access_token_file=path_of("line_channel_access_token_file"),
        model=_optional(raw, "model", str, DEFAULT_MODEL),
        max_tokens=_optional(raw, "max_tokens", int, DEFAULT_MAX_TOKENS),
        effort=_optional(raw, "effort", str, DEFAULT_EFFORT),
        cache_ttl=cache_ttl,
        recent_message_count=_optional(
            raw, "recent_message_count", int, DEFAULT_RECENT_MESSAGE_COUNT
        ),
        max_catch_up_messages=_optional(
            raw, "max_catch_up_messages", int, DEFAULT_MAX_CATCH_UP_MESSAGES
        ),
        summary_max_tokens=_optional(raw, "summary_max_tokens", int, DEFAULT_SUMMARY_MAX_TOKENS),
        patrol_interval_seconds=_optional(
            raw, "patrol_interval_seconds", int, DEFAULT_PATROL_INTERVAL_SECONDS
        ),
        max_tool_rounds=_optional(raw, "max_tool_rounds", int, DEFAULT_MAX_TOOL_ROUNDS),
        history_search_limit=_optional(
            raw, "history_search_limit", int, DEFAULT_HISTORY_SEARCH_LIMIT
        ),
        redelivered_answer_window_seconds=_optional(
            raw,
            "redelivered_answer_window_seconds",
            int,
            DEFAULT_REDELIVERED_ANSWER_WINDOW_SECONDS,
        ),
        required_member_user_id=_optional(raw, "required_member_user_id", str, None),
        allow_groups_with_required_member=_optional(
            raw, "allow_groups_with_required_member", bool, False
        ),
        alert_user_id=_optional(raw, "alert_user_id", str, None),
        intro_file=_optional_path(raw, "intro_file", base_dir, None),
        help_file=_optional_path(raw, "help_file", base_dir, None),
        help_keywords=_string_tuple(raw, "help_keywords", DEFAULT_HELP_KEYWORDS),
        itinerary_keywords=_string_tuple(raw, "itinerary_keywords", DEFAULT_ITINERARY_KEYWORDS),
        call_names=_string_tuple(raw, "call_names", ()),
        error_text=_optional(raw, "error_text", str, DEFAULT_ERROR_TEXT),
        wait_text=_optional(raw, "wait_text", str, DEFAULT_WAIT_TEXT),
        wait_min_push_left=_at_least(
            raw, "wait_min_push_left", DEFAULT_WAIT_MIN_PUSH_LEFT, minimum=0
        ),
        max_mentions_per_user_per_hour=_at_least(
            raw, "max_mentions_per_user_per_hour", DEFAULT_MAX_MENTIONS_PER_USER_PER_HOUR
        ),
        rate_limit_text=_optional(raw, "rate_limit_text", str, DEFAULT_RATE_LIMIT_TEXT),
        retention_days=_at_least(raw, "retention_days", DEFAULT_RETENTION_DAYS),
        web_search=_web_tool(
            raw, "web_search", DEFAULT_WEB_SEARCH_TYPE, DEFAULT_WEB_SEARCH_MAX_USES, None
        ),
        web_fetch=_web_tool(
            raw,
            "web_fetch",
            DEFAULT_WEB_FETCH_TYPE,
            DEFAULT_WEB_FETCH_MAX_USES,
            DEFAULT_WEB_FETCH_MAX_CONTENT_TOKENS,
        ),
        prices=_prices(_required(raw, "prices_usd", dict)),
        budget=_budget(_required(raw, "budget", dict)),
    )


def load_secrets(config: AgentConfig) -> Secrets:
    """Read the three secret files named by the configuration."""
    return Secrets(
        anthropic_api_key=_read_secret(config.anthropic_api_key_file, "anthropic_api_key_file"),
        line_channel_secret=_read_secret(
            config.line_channel_secret_file, "line_channel_secret_file"
        ),
        line_channel_access_token=_read_secret(
            config.line_channel_access_token_file, "line_channel_access_token_file"
        ),
    )


def _read_secret(path: Path, key: str) -> str:
    # The error names the setting, not the file's content.
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise ConfigError(f"cannot read the file named by {key}: {error.strerror}") from error
    if not value:
        raise ConfigError(f"the file named by {key} is empty")
    return value


def _web_tool(
    raw: dict[str, Any],
    key: str,
    default_type: str,
    default_max_uses: int,
    default_max_content_tokens: int | None,
) -> WebToolConfig | None:
    if key in raw and raw[key] is None:
        return None
    section = _optional(raw, key, dict, {})
    return WebToolConfig(
        type=_optional(section, "type", str, default_type),
        max_uses=_optional(section, "max_uses", int, default_max_uses),
        max_content_tokens=_optional(
            section, "max_content_tokens", int, default_max_content_tokens
        ),
    )


def _prices(section: dict[str, Any]) -> PriceConfig:
    return PriceConfig(
        input_per_mtok=_required(section, "input_per_mtok", float),
        output_per_mtok=_required(section, "output_per_mtok", float),
        cache_write_per_mtok=_required(section, "cache_write_per_mtok", float),
        cache_read_per_mtok=_required(section, "cache_read_per_mtok", float),
        web_search_per_thousand=_required(section, "web_search_per_thousand", float),
        cache_write_1h_per_mtok=_optional(section, "cache_write_1h_per_mtok", float, None),
        long_cache_write_1h_per_mtok=_optional(
            section, "long_cache_write_1h_per_mtok", float, None
        ),
        long_prompt_threshold_tokens=_optional(section, "long_prompt_threshold_tokens", int, None),
        long_input_per_mtok=_optional(section, "long_input_per_mtok", float, None),
        long_output_per_mtok=_optional(section, "long_output_per_mtok", float, None),
        long_cache_write_per_mtok=_optional(section, "long_cache_write_per_mtok", float, None),
        long_cache_read_per_mtok=_optional(section, "long_cache_read_per_mtok", float, None),
    )


def _budget(section: dict[str, Any]) -> BudgetConfig:
    return BudgetConfig(
        monthly_limit=_required(section, "monthly_limit", float),
        currency=_optional(section, "currency", str, DEFAULT_CURRENCY),
        currency_per_usd=_required(section, "currency_per_usd", float),
        estimated_input_tokens_per_request=_optional(
            section, "estimated_input_tokens_per_request", int, DEFAULT_ESTIMATED_INPUT_TOKENS
        ),
        exhausted_text=_optional(section, "exhausted_text", str, DEFAULT_EXHAUSTED_TEXT),
    )


def _string_tuple(raw: dict[str, Any], key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    values = _optional(raw, key, list, None)
    if values is None:
        return default
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ConfigError(f"{key} must be a list of non-empty strings")
    return tuple(value.strip() for value in values)


def _optional_path[T: Path | None](
    raw: dict[str, Any], key: str, base_dir: Path, default: T
) -> Path | T:
    value = _optional(raw, key, str, None)
    return default if value is None else base_dir / Path(value)


def _at_least(raw: dict[str, Any], key: str, default: int, *, minimum: int = 1) -> int:
    value: int = _optional(raw, key, int, default)
    if value < minimum:
        raise ConfigError(f"{key} must be at least {minimum}")
    return value


def _required(section: dict[str, Any], key: str, kind: type) -> Any:
    if key not in section or section[key] is None:
        raise ConfigError(f"missing setting: {key}")
    return _checked(section[key], key, kind)


def _optional(section: dict[str, Any], key: str, kind: type, default: Any) -> Any:
    if key not in section or section[key] is None:
        return default
    return _checked(section[key], key, kind)


def _checked(value: Any, key: str, kind: type) -> Any:
    # JSON has one number type: an integer is a valid float, a bool is not a number.
    if isinstance(value, bool) and kind is not bool:
        raise ConfigError(f"{key} must be a {kind.__name__}")
    if kind is float and isinstance(value, int):
        return float(value)
    if not isinstance(value, kind):
        raise ConfigError(f"{key} must be a {kind.__name__}")
    return value
