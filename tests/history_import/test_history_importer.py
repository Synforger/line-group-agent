from datetime import datetime
from pathlib import Path

from line_group_agent.history_import.history_importer import HistoryImporter
from line_group_agent.records.group_log import GroupLog, GroupMessage

GROUP = "Cgroup"
HISTORY = """\
2026/09/01(火)
10:00\tAki\tfirst
10:01\tSora\tsecond
2026/09/02(水)
09:00\tAki\tthird
"""


def texts(log: GroupLog) -> list[str]:
    return [m.text for m in log.list_recent(GROUP, 100)]


def test_the_messages_are_put_in_the_record_marked_as_imported(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    result = HistoryImporter(log).import_text(GROUP, HISTORY)
    assert (result.added_count, result.existing_count) == (3, 0)
    messages = log.list_recent(GROUP, 10)
    assert [m.text for m in messages] == ["first", "second", "third"]
    assert all(m.imported and m.user_id is None and not m.from_bot for m in messages)
    assert [m.display_name for m in messages] == ["Aki", "Sora", "Aki"]
    assert messages[0].message_id.startswith("import-")
    assert datetime.fromisoformat(messages[0].time).replace(tzinfo=None) == datetime(
        2026, 9, 1, 10, 0
    )


def test_importing_the_same_file_again_adds_nothing(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    importer = HistoryImporter(log)
    importer.import_text(GROUP, HISTORY)
    again = importer.import_text(GROUP, HISTORY)
    assert (again.added_count, again.existing_count) == (0, 3)
    assert texts(log) == ["first", "second", "third"]


def test_a_message_the_record_already_holds_is_not_added_even_with_seconds_and_an_id(
    tmp_path: Path,
) -> None:
    log = GroupLog(tmp_path)
    live = GroupMessage("2026-09-01T10:00:42+09:00", "real-1", "U1", "Aki", "first")
    log.add(GROUP, live)
    result = HistoryImporter(log).import_text(GROUP, HISTORY)
    assert result.existing_count == 1 and result.added_count == 2
    assert texts(log).count("first") == 1


def test_a_message_said_twice_in_a_minute_is_kept_twice_but_never_more_on_a_rerun(
    tmp_path: Path,
) -> None:
    log = GroupLog(tmp_path)
    twice = "2026/09/01\n10:00\tAki\tok\n10:00\tAki\tok\n"
    importer = HistoryImporter(log)
    assert importer.import_text(GROUP, twice).added_count == 2
    assert importer.import_text(GROUP, twice).added_count == 0
    ids = [m.message_id for m in log.list_recent(GROUP, 10)]
    assert len(set(ids)) == 2


def test_old_messages_go_before_the_newer_ones_already_in_the_record(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add(GROUP, GroupMessage("2026-11-18T12:00:00+09:00", "r1", "U1", "Aki", "live one"))
    log.add(GROUP, GroupMessage("2026-11-18T12:05:00+09:00", "r2", "U1", "Aki", "live two"))
    HistoryImporter(log).import_text(GROUP, HISTORY)
    assert texts(log) == ["first", "second", "third", "live one", "live two"]


def test_an_imported_message_in_the_middle_lands_between_live_ones(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add(GROUP, GroupMessage("2026-09-01T09:00:00+09:00", "r1", "U1", "Aki", "before"))
    log.add(GROUP, GroupMessage("2026-09-03T09:00:00+09:00", "r2", "U1", "Aki", "after"))
    HistoryImporter(log).import_text(GROUP, HISTORY)
    assert texts(log) == ["before", "first", "second", "third", "after"]


def test_the_order_of_the_records_own_rows_is_not_changed(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    for number, text in enumerate(["b", "a", "c"]):
        log.add(
            GROUP, GroupMessage(f"2026-11-18T12:00:0{number}+09:00", f"r{number}", None, "X", text)
        )
    log.add(GROUP, GroupMessage("not a time", "r9", None, "X", "odd one"))
    HistoryImporter(log).import_text(GROUP, HISTORY)
    assert texts(log)[3:] == ["b", "a", "c", "odd one"]


def test_the_result_counts_what_was_skipped(tmp_path: Path) -> None:
    text = HISTORY + "garbage line\n09:30\tAki joined.\n"
    result = HistoryImporter(GroupLog(tmp_path)).import_text(GROUP, text)
    assert (result.added_count, result.notice_count, result.unrecognized_count) == (3, 1, 1)


def test_imported_messages_survive_the_retention_sweep_but_live_ones_do_not(
    tmp_path: Path,
) -> None:
    log = GroupLog(tmp_path)
    log.add(GROUP, GroupMessage("2026-09-01T10:00:00+09:00", "r1", "U1", "Aki", "old live"))
    HistoryImporter(log).import_text(GROUP, HISTORY.replace("first", "old import"))
    cutoff = datetime.fromisoformat("2026-11-01T00:00:00+09:00")
    removed = log.remove_older_than(GROUP, cutoff, keep_since=None)
    assert [m.text for m in removed] == ["old live"]
    assert "old import" in texts(log)


def test_an_imported_message_can_still_be_deleted_by_id(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    HistoryImporter(log).import_text(GROUP, HISTORY)
    first = log.list_recent(GROUP, 10)[0]
    assert [m.text for m in log.remove(GROUP, {first.message_id})] == ["first"]
