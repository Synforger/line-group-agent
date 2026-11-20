import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

from line_group_agent.spend.shared_spend_reader import SharedSpendReader
from tests.fakes import make_config

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def reader_for(tmp_path: Path, *names: str) -> SharedSpendReader:
    budget = {
        "monthly_limit": 1000,
        "currency": "JPY",
        "currency_per_usd": 150,
        "shared_spend_files": list(names),
    }
    config = make_config(tmp_path, budget=budget)
    return SharedSpendReader(config.budget, clock=lambda: NOW)


def write_figure(path: Path, **fields: object) -> None:
    figure = {"month": "2026-11", "spent": 10, "limit": 500, "currency": "JPY"}
    figure.update(fields)
    path.write_text(json.dumps(figure))


def test_no_files_add_nothing(tmp_path: Path) -> None:
    assert reader_for(tmp_path).total() == 0.0


def test_the_figures_of_all_files_are_added(tmp_path: Path) -> None:
    write_figure(tmp_path / "a.json", spent=10.5)
    write_figure(tmp_path / "b.json", spent=4)
    assert reader_for(tmp_path, "a.json", "b.json").total() == 14.5


def test_a_file_is_read_again_every_time(tmp_path: Path) -> None:
    write_figure(tmp_path / "a.json", spent=10)
    reader = reader_for(tmp_path, "a.json")
    assert reader.total() == 10
    write_figure(tmp_path / "a.json", spent=25)
    assert reader.total() == 25


def test_a_missing_file_counts_as_zero(tmp_path: Path) -> None:
    write_figure(tmp_path / "a.json", spent=7)
    assert reader_for(tmp_path, "a.json", "not-yet.json").total() == 7


def test_a_file_of_last_month_counts_as_zero(tmp_path: Path) -> None:
    write_figure(tmp_path / "a.json", month="2026-10", spent=900)
    assert reader_for(tmp_path, "a.json").total() == 0.0


def test_a_relative_path_is_solved_from_the_configuration_folder(tmp_path: Path) -> None:
    (tmp_path / "other").mkdir()
    write_figure(tmp_path / "other" / "spend.json", spent=3)
    assert reader_for(tmp_path, "other/spend.json").total() == 3


def test_a_file_in_another_currency_gives_no_answer_and_is_logged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    write_figure(tmp_path / "a.json", currency="USD")
    with caplog.at_level(logging.WARNING):
        assert reader_for(tmp_path, "a.json").total() is None
    assert "a.json" in caplog.text and "currency" in caplog.text


@pytest.mark.parametrize(
    "text",
    [
        "{not json",
        "[]",
        json.dumps({"month": "2026-11", "currency": "JPY"}),
        json.dumps({"spent": 1, "currency": "JPY"}),
        json.dumps({"month": "2026-11", "spent": 1}),
        json.dumps({"month": "2026-11", "spent": "12", "currency": "JPY"}),
        json.dumps({"month": "2026-11", "spent": True, "currency": "JPY"}),
        json.dumps({"month": "2026-11", "spent": None, "currency": "JPY"}),
        json.dumps({"month": "2026-11", "spent": -1, "currency": "JPY"}),
        '{"month": "2026-11", "spent": NaN, "currency": "JPY"}',
    ],
)
def test_a_file_that_cannot_be_used_gives_no_answer(tmp_path: Path, text: str) -> None:
    (tmp_path / "a.json").write_text(text)
    write_figure(tmp_path / "b.json", spent=1)
    assert reader_for(tmp_path, "b.json", "a.json").total() is None


def test_a_path_that_is_a_folder_gives_no_answer(tmp_path: Path) -> None:
    (tmp_path / "a.json").mkdir()
    assert reader_for(tmp_path, "a.json").total() is None
