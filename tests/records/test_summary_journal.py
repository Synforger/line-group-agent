from datetime import date
from pathlib import Path

import pytest

from line_group_agent.records.summary_journal import SummaryJournal


def test_a_summary_is_written_under_the_groups_journal_and_read_back(tmp_path: Path) -> None:
    journal = SummaryJournal(tmp_path)
    path = journal.write("Ca", 2, "  Decided: Kyoto.  ", date(2026, 11, 18))
    assert path == tmp_path / "groups" / "Ca" / "journal" / "2026-11-18-gen2.md"
    assert path.read_text() == "Decided: Kyoto.\n"
    text, written_at = journal.read("Ca", 2) or ("", None)
    assert text == "Decided: Kyoto." and written_at is not None


def test_a_generation_without_a_summary_reads_as_none(tmp_path: Path) -> None:
    journal = SummaryJournal(tmp_path)
    assert journal.read("Ca", 1) is None
    journal.write("Ca", 11, "x", date(2026, 11, 18))
    assert journal.read("Ca", 1) is None


def test_the_latest_file_of_a_generation_counts(tmp_path: Path) -> None:
    journal = SummaryJournal(tmp_path)
    journal.write("Ca", 1, "old", date(2026, 11, 17))
    journal.write("Ca", 1, "new", date(2026, 11, 18))
    assert (journal.read("Ca", 1) or ("",))[0] == "new"


def test_a_group_id_cannot_leave_the_folder(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SummaryJournal(tmp_path).write("../x", 1, "x", date(2026, 11, 18))
