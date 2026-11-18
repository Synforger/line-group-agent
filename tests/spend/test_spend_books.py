import json
from pathlib import Path

from line_group_agent.config.settings_store import SettingsStore
from line_group_agent.spend.spend_books import SpendBooks
from line_group_agent.spend.spend_ledger import SpendLedger
from tests.fakes import make_config


def books_for(tmp_path: Path, group_count: int, **overrides: object) -> tuple[SpendBooks, Path]:
    config = make_config(tmp_path, **overrides)
    overall = SpendLedger(config.state_dir / "spend.json", config.budget)
    overall.open()
    settings = SettingsStore(config.settings_file)
    return SpendBooks(
        overall, config.state_dir, config.budget, settings, lambda: group_count
    ), config.settings_file


def test_each_group_may_spend_the_overall_limit_divided_by_the_group_count(tmp_path: Path) -> None:
    books, _ = books_for(tmp_path, 4)
    assert books.group_figure("Ca")["limit"] == 250.0
    assert books.can_afford("Ca", 250.0)
    assert not books.can_afford("Ca", 250.1)


def test_a_cost_counts_for_the_group_and_for_the_whole(tmp_path: Path) -> None:
    books, _ = books_for(tmp_path, 2)
    books.add("Ca", 100)
    books.add("Cb", 30)
    assert books.group_figure("Ca")["spent"] == 100
    assert books.group_figure("Cb")["spent"] == 30
    assert books.overall.spent == 130
    assert not books.can_afford("Ca", 401)
    assert books.can_afford("Cb", 400)


def test_the_whole_limit_stops_a_group_that_is_within_its_own(tmp_path: Path) -> None:
    books, _ = books_for(tmp_path, 2)
    books.add("Ca", 500)
    books.add("Cb", 450)
    assert not books.can_afford("Cb", 60)
    assert books.can_afford("Cb", 50)


def test_the_group_figure_lives_in_the_groups_folder(tmp_path: Path) -> None:
    books, _ = books_for(tmp_path, 1)
    books.add("Ca", 5)
    saved = json.loads((tmp_path / "state" / "groups" / "Ca" / "spend.json").read_text())
    assert saved["spent"] == 5 and saved["limit"] == 1000.0 and saved["currency"] == "JPY"


def test_a_group_figure_survives_a_restart(tmp_path: Path) -> None:
    books, _ = books_for(tmp_path, 1)
    books.add("Ca", 7)
    again, _ = books_for(tmp_path, 1)
    assert again.group_figure("Ca")["spent"] == 7


def test_the_settings_file_sets_the_limit_in_dollars_converted_to_the_currency(
    tmp_path: Path,
) -> None:
    books, settings_file = books_for(tmp_path, 2)
    settings_file.write_text(json.dumps({"monthly_budget_usd": 10}))
    assert books.overall_limit() == 1500.0
    assert books.group_figure("Ca")["limit"] == 750.0
    assert json.loads(books.overall.path.read_text())["limit"] == 1500.0


def test_a_changed_group_count_changes_the_group_limits(tmp_path: Path) -> None:
    count = [1]
    config = make_config(tmp_path)
    overall = SpendLedger(config.state_dir / "spend.json", config.budget)
    overall.open()
    books = SpendBooks(
        overall, config.state_dir, config.budget, SettingsStore(None), lambda: count[0]
    )
    assert books.group_figure("Ca")["limit"] == 1000.0
    count[0] = 4
    assert books.group_figure("Ca")["limit"] == 250.0
