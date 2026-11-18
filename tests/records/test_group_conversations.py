from datetime import date
from pathlib import Path

import pytest

from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.records.summary_journal import SummaryJournal


def registry(tmp_path: Path) -> GroupConversations:
    return GroupConversations(tmp_path, GroupLog(tmp_path), SummaryJournal(tmp_path))


def test_the_listed_groups_and_the_groups_with_a_record_are_known(tmp_path: Path) -> None:
    GroupLog(tmp_path).add("Cold", GroupMessage("t", "1", "U", "A", "hi"))
    known = registry(tmp_path)
    known.open(["Clisted"])
    assert known.count() == 2
    assert [c.name for c in known.list()] == ["g-clisted", "g-cold"]


def test_a_group_is_opened_once_and_its_record_is_named_from_its_id(tmp_path: Path) -> None:
    known = registry(tmp_path)
    assert known.get("Cabc") is known.get("Cabc")
    assert known.get("Cabc").log.path == tmp_path / "conversations" / "g-cabc.jsonl"


def test_a_summary_not_yet_used_waits_again_after_a_restart(tmp_path: Path) -> None:
    first = registry(tmp_path).get("Ca")
    first.add_user("x")
    SummaryJournal(tmp_path).write("Ca", 1, "Decided: Kyoto.", date(2026, 11, 18))
    waiting = registry(tmp_path).get("Ca")
    assert waiting.pending_summary == "Decided: Kyoto." and waiting.shown_generation == 2
    assert waiting.last_rollover_at is not None


def test_the_last_time_a_group_spoke_is_recovered_from_its_record(tmp_path: Path) -> None:
    GroupLog(tmp_path).add("Ca", GroupMessage("2026-11-18T12:00:00+09:00", "1", "U", "A", "hi"))
    activity = registry(tmp_path).get("Ca").last_activity_at
    assert activity is not None and activity.hour == 12


def test_a_group_id_that_could_leave_the_folder_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        registry(tmp_path).get("../x")


def test_the_generation_comes_from_the_journal_after_old_rows_expired(tmp_path: Path) -> None:
    journal = SummaryJournal(tmp_path)
    journal.write("Ca", 1, "First summary.", date(2026, 10, 1))
    journal.write("Ca", 2, "Second summary.", date(2026, 10, 20))
    first = registry(tmp_path).get("Ca")
    first.add_user("Group messages ...")
    first.add_user("Summary of the conversation so far\nSecond summary.\n\nnext turn")
    # The record now starts at the summary row that opened generation 3.
    first.log.replace_rows(first.log.read_rows()[1:])
    reopened = registry(tmp_path).get("Ca")
    assert reopened.generation == 3
    assert reopened.pending_summary is None and reopened.shown_generation == 3


def test_a_summary_the_record_has_not_opened_with_waits_in_its_own_generation(
    tmp_path: Path,
) -> None:
    journal = SummaryJournal(tmp_path)
    journal.write("Ca", 1, "First summary.", date(2026, 10, 1))
    journal.write("Ca", 2, "Second summary.", date(2026, 10, 20))
    first = registry(tmp_path).get("Ca")
    first.add_user("Summary of the conversation so far\nFirst summary.\n\nturn of generation 2")
    reopened = registry(tmp_path).get("Ca")
    assert reopened.generation == 2
    assert reopened.pending_summary == "Second summary."
    assert reopened.shown_generation == 3


def test_a_record_with_no_journal_keeps_the_generation_counted_from_its_rows(
    tmp_path: Path,
) -> None:
    first = registry(tmp_path).get("Ca")
    first.add_user("one")
    first.add_assistant(
        {"id": "m", "role": "assistant", "content": [], "usage": {"input_tokens": 1}}
    )
    first.add_user("Summary of the conversation so far\nx\n\ntwo")
    assert registry(tmp_path).get("Ca").generation == 2
