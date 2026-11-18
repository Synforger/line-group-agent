from pathlib import Path

import pytest

from line_group_agent.spend.pricing import (
    mention_estimate_usd,
    request_estimate_usd,
    to_currency,
    usage_cost_usd,
)
from tests.fakes import make_config


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


def test_a_request_estimate_is_the_estimated_prompt_a_full_answer_and_all_searches(
    tmp_path: Path,
) -> None:
    config = make_config(tmp_path)
    expected = (20_000 * 0.10 + 1024 * 0.50) / 1e6 + 3 * 0.01
    assert request_estimate_usd(config) == pytest.approx(expected)


def test_a_mention_estimate_covers_every_request_of_the_tool_loop(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert mention_estimate_usd(config) == pytest.approx(5 * request_estimate_usd(config))


def test_without_web_search_the_estimate_has_no_search_cost(tmp_path: Path) -> None:
    config = make_config(tmp_path, web_search=None)
    assert request_estimate_usd(config) == pytest.approx((20_000 * 0.10 + 1024 * 0.50) / 1e6)


def test_dollars_become_the_reported_currency(tmp_path: Path) -> None:
    assert to_currency(2.0, make_config(tmp_path).budget) == pytest.approx(300.0)
