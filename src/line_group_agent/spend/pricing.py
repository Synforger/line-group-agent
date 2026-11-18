"""What a request costs: from the `usage` of an answer, or estimated before calling.

Pure calculation; the prices come from the configuration. Called by the answerer.
"""

from __future__ import annotations

from typing import Any

from line_group_agent.config.agent_config import AgentConfig, BudgetConfig, PriceConfig

TOKENS_PER_MTOK = 1_000_000
SEARCHES_PER_PRICE_UNIT = 1000


def usage_cost_usd(usage: dict[str, Any], prices: PriceConfig) -> float:
    """Return the dollar cost of one answer from its `usage` (tokens and web searches)."""
    input_tokens = _count(usage, "input_tokens")
    output_tokens = _count(usage, "output_tokens")
    cache_write_tokens = _count(usage, "cache_creation_input_tokens")
    cache_read_tokens = _count(usage, "cache_read_input_tokens")
    server_tools = usage.get("server_tool_use") or {}
    searches = _count(server_tools, "web_search_requests")

    prompt_tokens = input_tokens + cache_write_tokens + cache_read_tokens
    card = _rate_card(prices, prompt_tokens)
    token_cost = (
        input_tokens * card["input"]
        + output_tokens * card["output"]
        + cache_write_tokens * card["cache_write"]
        + cache_read_tokens * card["cache_read"]
    ) / TOKENS_PER_MTOK
    return token_cost + searches * prices.web_search_per_thousand / SEARCHES_PER_PRICE_UNIT


def request_estimate_usd(config: AgentConfig) -> float:
    """Return the most one request is expected to cost: the estimated prompt, a full
    `max_tokens` answer and every web search it may run."""
    prompt_tokens = config.budget.estimated_input_tokens_per_request
    card = _rate_card(config.prices, prompt_tokens)
    token_cost = (
        prompt_tokens * card["input"] + config.max_tokens * card["output"]
    ) / TOKENS_PER_MTOK
    searches = config.web_search.max_uses if config.web_search else 0
    return token_cost + searches * config.prices.web_search_per_thousand / SEARCHES_PER_PRICE_UNIT


def mention_estimate_usd(config: AgentConfig) -> float:
    """Return the most one mention is expected to cost: every request the tool loop
    may make (the first one plus one per tool round)."""
    return (config.max_tool_rounds + 1) * request_estimate_usd(config)


def to_currency(usd: float, budget: BudgetConfig) -> float:
    """Convert dollars into the currency the spend file reports."""
    return usd * budget.currency_per_usd


def _rate_card(prices: PriceConfig, prompt_tokens: int) -> dict[str, float]:
    # Some models price a whole request higher once its prompt passes a threshold.
    is_long = (
        prices.long_prompt_threshold_tokens is not None
        and prompt_tokens > prices.long_prompt_threshold_tokens
    )
    if is_long:
        return {
            "input": _or(prices.long_input_per_mtok, prices.input_per_mtok),
            "output": _or(prices.long_output_per_mtok, prices.output_per_mtok),
            "cache_write": _or(prices.long_cache_write_per_mtok, prices.cache_write_per_mtok),
            "cache_read": _or(prices.long_cache_read_per_mtok, prices.cache_read_per_mtok),
        }
    return {
        "input": prices.input_per_mtok,
        "output": prices.output_per_mtok,
        "cache_write": prices.cache_write_per_mtok,
        "cache_read": prices.cache_read_per_mtok,
    }


def _or(value: float | None, fallback: float) -> float:
    return fallback if value is None else value


def _count(section: dict[str, Any], key: str) -> int:
    value = section.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
