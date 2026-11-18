import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from line_group_agent.spend.spend_ledger import SpendLedger, SpendLedgerError
from tests.fakes import make_config

TOKYO = timezone(timedelta(hours=9))


class Clock:
    def __init__(self, moment: datetime) -> None:
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment


def ledger_at(tmp_path: Path, clock: Clock) -> SpendLedger:
    return SpendLedger(tmp_path / "spend.json", make_config(tmp_path).budget, clock=clock)


def read(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "spend.json").read_text())


def test_the_file_has_the_agreed_shape(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 11, 18, 12, 0, tzinfo=TOKYO))
    ledger = ledger_at(tmp_path, clock)
    ledger.open()
    ledger.add(12.5)
    assert read(tmp_path) == {
        "month": "2026-11",
        "spent": 12.5,
        "limit": 1000.0,
        "currency": "JPY",
        "updated_at": "2026-11-18T12:00:00+09:00",
    }


def test_each_write_replaces_the_whole_file_and_leaves_no_temporary(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, Clock(datetime(2026, 11, 18, tzinfo=TOKYO)))
    ledger.open()
    ledger.add(1)
    ledger.add(2)
    assert read(tmp_path)["spent"] == 3
    assert [p.name for p in tmp_path.iterdir()] == ["spend.json"]


def test_open_carries_this_months_figure(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 11, 18, tzinfo=TOKYO))
    first = ledger_at(tmp_path, clock)
    first.open()
    first.add(40)
    second = ledger_at(tmp_path, clock)
    second.open()
    assert second.spent == 40


def test_open_starts_from_zero_on_a_file_of_another_month(tmp_path: Path) -> None:
    (tmp_path / "spend.json").write_text(json.dumps({"month": "2026-10", "spent": 999}))
    ledger = ledger_at(tmp_path, Clock(datetime(2026, 11, 1, tzinfo=TOKYO)))
    ledger.open()
    assert ledger.spent == 0
    assert read(tmp_path)["month"] == "2026-11"


def test_a_new_month_starts_from_zero_while_running(tmp_path: Path) -> None:
    clock = Clock(datetime(2026, 11, 30, 23, 59, tzinfo=TOKYO))
    ledger = ledger_at(tmp_path, clock)
    ledger.open()
    ledger.add(500)
    clock.moment = datetime(2026, 12, 1, 0, 0, tzinfo=TOKYO)
    assert ledger.spent == 0
    assert read(tmp_path)["month"] == "2026-12"
    ledger.add(3)
    assert read(tmp_path)["spent"] == 3


def test_can_afford_stops_at_the_limit(tmp_path: Path) -> None:
    ledger = ledger_at(tmp_path, Clock(datetime(2026, 11, 18, tzinfo=TOKYO)))
    ledger.open()
    ledger.add(990)
    assert ledger.can_afford(10)
    assert not ledger.can_afford(10.01)


def test_an_unreadable_file_stops_start(tmp_path: Path) -> None:
    (tmp_path / "spend.json").write_text("{broken")
    with pytest.raises(SpendLedgerError):
        ledger_at(tmp_path, Clock(datetime(2026, 11, 18, tzinfo=TOKYO))).open()
