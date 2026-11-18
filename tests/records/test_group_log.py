import json
from pathlib import Path

import pytest

from line_group_agent.records.group_log import GroupLog, GroupMessage


def message(number: int, text: str) -> GroupMessage:
    return GroupMessage(
        time=f"2026-11-18T12:00:{number:02d}+09:00",
        message_id=str(number),
        user_id="U1",
        display_name="Aki",
        text=text,
    )


def test_each_message_is_one_line_with_the_agreed_fields(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", message(1, "hello"))
    path = tmp_path / "groups" / "Cgroup" / "messages.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows == [
        {
            "time": "2026-11-18T12:00:01+09:00",
            "message_id": "1",
            "user_id": "U1",
            "display_name": "Aki",
            "text": "hello",
        }
    ]


def test_add_only_appends(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    for number in range(3):
        log.add("Cgroup", message(number, f"text {number}"))
    path = tmp_path / "groups" / "Cgroup" / "messages.jsonl"
    assert len(path.read_text().splitlines()) == 3


def test_list_recent_is_the_last_n_oldest_first(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    for number in range(5):
        log.add("Cgroup", message(number, f"text {number}"))
    recent = log.list_recent("Cgroup", 2)
    assert [m.message_id for m in recent] == ["3", "4"]


def test_list_recent_can_leave_out_the_mention_itself(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    for number in range(3):
        log.add("Cgroup", message(number, f"text {number}"))
    recent = log.list_recent("Cgroup", 5, exclude_message_id="2")
    assert [m.message_id for m in recent] == ["0", "1"]


def test_list_recent_of_an_empty_group_is_empty(tmp_path: Path) -> None:
    assert GroupLog(tmp_path).list_recent("Cgroup", 30) == []


def test_search_is_any_case_newest_first_and_limited(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", message(1, "Hotel in Kyoto"))
    log.add("Cgroup", message(2, "train times"))
    log.add("Cgroup", message(3, "another HOTEL idea"))
    log.add("Cgroup", message(4, "hotel booked"))
    found = log.search("Cgroup", "hotel", 2)
    assert [m.message_id for m in found] == ["4", "3"]


def test_search_with_an_empty_query_finds_nothing(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", message(1, "anything"))
    assert log.search("Cgroup", "  ", 20) == []


def test_groups_are_kept_apart(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cone", message(1, "one"))
    assert log.list_recent("Ctwo", 10) == []


@pytest.mark.parametrize("group_id", ["../escape", "a/b", ""])
def test_a_group_id_cannot_leave_the_state_folder(tmp_path: Path, group_id: str) -> None:
    with pytest.raises(ValueError):
        GroupLog(tmp_path).add(group_id, message(1, "x"))


def test_has_message_finds_a_recorded_message_id(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    assert not log.has_message("Cgroup", "1")
    log.add("Cgroup", message(1, "hello"))
    assert log.has_message("Cgroup", "1")
    assert not log.has_message("Cgroup", "2")
