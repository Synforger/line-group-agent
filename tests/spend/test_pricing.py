from pathlib import Path

import pytest

from line_group_agent.config.agent_config import parse_config
from line_group_agent.spend.pricing import (
    mention_estimate_usd,
    request_estimate_usd,
    to_currency,
    usage_cost_usd,
)
from tests.fakes import make_config, raw_config


def test_cost_counts_every_kind_of_token_and_each_search(tmp_path: Path) -> None:
    prices = make_config(tmp_path).prices
    usage = {
        "input_tokens": 10_000,
        "output_tokens": 1_000,
        "cache_creation_input_tokens": 2_000,
        "cache_read_input_tokens": 4_000,
        "server_tool_use": {"web_search_requests": 2},
    }
    expected = (10_000 * 0.10 + 1_000 * 0.50 + 2_000 * 0.125 + 4_000 * 0.01) / 1e6 + 2 * 0.01
    assert usage_cost_usd(usage, prices) == pytest.approx(expected)


def test_a_long_prompt_is_priced_on_the_long_card(tmp_path: Path) -> None:
    prices = make_config(tmp_path).prices
    usage = {"input_tokens": 90_000, "cache_read_input_tokens": 20_000, "output_tokens": 1_000}
    expected = (90_000 * 0.50 + 20_000 * 0.05 + 1_000 * 2.50) / 1e6
    assert usage_cost_usd(usage, prices) == pytest.approx(expected)


def test_missing_counts_are_zero(tmp_path: Path) -> None:
    assert usage_cost_usd({}, make_config(tmp_path).prices) == 0


def test_a_request_estimate_is_the_prompt_written_to_the_cache_a_full_answer_and_all_searches(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    expected = (20_000 * 0.20 + 1024 * 0.50) / 1e6 + 3 * 0.01
    assert request_estimate_usd(config) == pytest.approx(expected)


def test_a_five_minute_cache_estimates_with_the_five_minute_write_price(tmp_path: Path) -> None:
    config = make_config(tmp_path, cache_ttl="5m", web_search=None)
    assert request_estimate_usd(config) == pytest.approx((20_000 * 0.125 + 1024 * 0.50) / 1e6)


def test_the_estimate_grows_with_the_conversation_and_can_leave_out_searches(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    expected = (60_000 * 0.20 + 2_000 * 0.50) / 1e6
    got = request_estimate_usd(config, context_tokens=60_000, max_tokens=2_000, with_searches=False)
    assert got == pytest.approx(expected)


def test_a_mention_estimate_covers_every_request_of_the_tool_loop(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert mention_estimate_usd(config) == pytest.approx(5 * request_estimate_usd(config))


def test_without_web_search_the_estimate_has_no_search_cost(tmp_path: Path) -> None:
    config = make_config(tmp_path, web_search=None)
    assert request_estimate_usd(config) == pytest.approx((20_000 * 0.20 + 1024 * 0.50) / 1e6)


def test_one_hour_cache_writes_cost_twice_the_input_price_unless_the_config_says_so(
    tmp_path: Path,
) -> None:
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 10_000}
    prices = make_config(tmp_path).prices
    assert usage_cost_usd(usage, prices, cache_ttl="5m") == pytest.approx(10_000 * 0.125 / 1e6)
    assert usage_cost_usd(usage, prices, cache_ttl="1h") == pytest.approx(10_000 * 0.20 / 1e6)
    long_usage = {**usage, "input_tokens": 100_000}
    long_cost = (100_000 * 0.50 + 10_000 * 1.0) / 1e6
    assert usage_cost_usd(long_usage, prices, cache_ttl="1h") == pytest.approx(long_cost)


def test_a_reported_split_of_cache_writes_is_charged_per_lifetime(tmp_path: Path) -> None:
    usage = {
        "cache_creation_input_tokens": 10_000,
        "cache_creation": {"ephemeral_5m_input_tokens": 4_000, "ephemeral_1h_input_tokens": 6_000},
    }
    expected = (4_000 * 0.125 + 6_000 * 0.20) / 1e6
    assert usage_cost_usd(usage, make_config(tmp_path).prices, cache_ttl="5m") == pytest.approx(
        expected
    )


def test_a_configured_one_hour_price_wins(tmp_path: Path) -> None:
    raw = raw_config(tmp_path)
    raw["prices_usd"]["cache_write_1h_per_mtok"] = 0.3
    prices = parse_config(raw, tmp_path).prices
    usage = {"cache_creation_input_tokens": 50_000}
    assert usage_cost_usd(usage, prices, cache_ttl="1h") == pytest.approx(50_000 * 0.3 / 1e6)


def test_dollars_become_the_reported_currency(tmp_path: Path) -> None:
    assert to_currency(2.0, make_config(tmp_path).budget) == pytest.approx(300.0)
