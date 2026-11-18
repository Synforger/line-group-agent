import json
from datetime import datetime
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
            "from_bot": False,
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


def test_a_bot_reply_reads_back_marked(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", message(1, "hello"))
    log.add(
        "Cgroup",
        GroupMessage(
            time="2026-11-18T12:00:02+09:00",
            message_id="bot-1",
            user_id=None,
            display_name=None,
            text="hi there",
            from_bot=True,
        ),
    )
    first, second = log.list_recent("Cgroup", 10)
    assert not first.from_bot and second.from_bot


def msg(number: int, *, from_bot: bool = False) -> GroupMessage:
    return GroupMessage(
        f"2026-11-18T12:00:0{number}+09:00", f"m{number}", "U1", "Aki", f"t{number}", from_bot
    )


def test_messages_since_the_last_reply_leave_out_the_bots_own(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    for number in range(1, 4):
        log.add("Ca", msg(number))
    log.add("Ca", msg(4, from_bot=True))
    for number in range(5, 8):
        log.add("Ca", msg(number))
    since = log.list_since_turn("Ca", 10, after_message_id=None, exclude_message_id="m7")
    assert [m.message_id for m in since] == ["m5", "m6"]


def test_the_turn_ends_at_the_mention_taken_up_when_no_reply_followed(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    for number in range(1, 7):
        log.add("Ca", msg(number))
    since = log.list_since_turn("Ca", 10, after_message_id="m3", exclude_message_id="m6")
    assert [m.message_id for m in since] == ["m4", "m5"]


def test_without_a_reply_or_a_known_turn_the_last_messages_up_to_the_limit_count(
    tmp_path: Path,
) -> None:
    log = GroupLog(tmp_path)
    for number in range(1, 6):
        log.add("Ca", msg(number))
    since = log.list_since_turn("Ca", 2, after_message_id=None)
    assert [m.message_id for m in since] == ["m4", "m5"]
    assert log.list_since_turn("Ca", 0, after_message_id=None) == []


def test_the_latest_time_and_the_known_groups(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    assert log.last_message_time("Ca") is None and log.list_group_ids() == []
    log.add("Cb", msg(1))
    log.add("Ca", msg(2))
    assert log.last_message_time("Ca") == "2026-11-18T12:00:02+09:00"
    assert log.list_group_ids() == ["Ca", "Cb"]


def log_with(tmp_path: Path, *messages: GroupMessage) -> GroupLog:
    group_log = GroupLog(tmp_path)
    for message in messages:
        group_log.add("Ca", message)
    return group_log


def posted(
    number: int, text: str, user: str | None = "U1", *, time: str = "2026-11-18T12:00:00+09:00"
) -> GroupMessage:
    return GroupMessage(time, f"m{number}", user, "Aki", text, from_bot=user is None)


def test_only_the_requesters_own_messages_and_the_bots_replies_can_be_found_to_delete(
    tmp_path: Path,
) -> None:
    group_log = log_with(
        tmp_path,
        posted(1, "my kyoto idea", "U1"),
        posted(2, "bo's kyoto idea", "U2"),
        posted(3, "the bot's kyoto answer", None),
        posted(4, "unrelated", "U1"),
    )
    found = group_log.list_deletable("Ca", "KYOTO", 10, requester_user_id="U1")
    assert [m.message_id for m in found] == ["m3", "m1"]


def test_the_request_itself_is_never_found_and_the_limit_counts_newest_first(
    tmp_path: Path,
) -> None:
    group_log = log_with(tmp_path, *(posted(n, f"kyoto {n}") for n in range(1, 5)))
    found = group_log.list_deletable(
        "Ca", "kyoto", 2, requester_user_id="U1", exclude_message_id="m4"
    )
    assert [m.message_id for m in found] == ["m3", "m2"]


def test_without_a_known_requester_only_the_bots_replies_can_be_found(tmp_path: Path) -> None:
    group_log = log_with(tmp_path, posted(1, "kyoto", "U1"), posted(2, "kyoto", None))
    found = group_log.list_deletable("Ca", "kyoto", 10, requester_user_id=None)
    assert [m.message_id for m in found] == ["m2"]


def test_an_empty_query_finds_nothing_to_delete(tmp_path: Path) -> None:
    group_log = log_with(tmp_path, posted(1, "kyoto"))
    assert group_log.list_deletable("Ca", "  ", 10, requester_user_id="U1") == []


def test_removed_messages_are_gone_from_the_file_and_returned(tmp_path: Path) -> None:
    group_log = log_with(tmp_path, posted(1, "a"), posted(2, "b"), posted(3, "c"))
    removed = group_log.remove("Ca", {"m1", "m3"})
    assert [m.text for m in removed] == ["a", "c"]
    assert [m.text for m in group_log.list_recent("Ca", 10)] == ["b"]
    assert not any(tmp_path.rglob("*.tmp"))


def test_removing_ids_that_are_not_there_leaves_the_file_untouched(tmp_path: Path) -> None:
    group_log = log_with(tmp_path, posted(1, "a"))
    path = tmp_path / "groups" / "Ca" / "messages.jsonl"
    before = path.stat().st_mtime_ns
    assert group_log.remove("Ca", {"m9"}) == []
    assert path.stat().st_mtime_ns == before


def test_messages_older_than_the_cutoff_are_removed_except_the_running_conversations(
    tmp_path: Path,
) -> None:
    group_log = log_with(
        tmp_path,
        posted(1, "old", time="2026-10-01T12:00:00+09:00"),
        posted(2, "old but live", time="2026-10-20T12:00:00+09:00"),
        posted(3, "recent", time="2026-11-17T12:00:00+09:00"),
    )
    cutoff = datetime.fromisoformat("2026-10-19T12:00:00+09:00")
    keep_since = datetime.fromisoformat("2026-10-15T00:00:00+09:00")
    assert [m.text for m in group_log.remove_older_than("Ca", cutoff, keep_since=keep_since)] == [
        "old"
    ]
    assert [m.text for m in group_log.list_recent("Ca", 10)] == ["old but live", "recent"]


def test_without_a_running_conversation_every_message_before_the_cutoff_goes(
    tmp_path: Path,
) -> None:
    group_log = log_with(
        tmp_path,
        posted(1, "old", time="2026-10-01T12:00:00+09:00"),
        posted(2, "bad time", time="not a time"),
        posted(3, "recent", time="2026-11-17T12:00:00+09:00"),
    )
    cutoff = datetime.fromisoformat("2026-10-19T12:00:00+09:00")
    group_log.remove_older_than("Ca", cutoff, keep_since=None)
    assert [m.text for m in group_log.list_recent("Ca", 10)] == ["bad time", "recent"]


def test_a_photo_row_holds_the_file_name_and_other_rows_do_not(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", GroupMessage("t", "1", "U1", "Aki", "[写真]", image_file="1.jpg"))
    log.add("Cgroup", message(2, "hello"))
    path = tmp_path / "groups" / "Cgroup" / "messages.jsonl"
    first, second = [json.loads(line) for line in path.read_text().splitlines()]
    assert first["image_file"] == "1.jpg" and "image_file" not in second
    assert [m.image_file for m in log.list_recent("Cgroup", 10)] == ["1.jpg", None]


def keep_photo(tmp_path: Path, name: str) -> Path:
    path = tmp_path / "groups" / "Cgroup" / "images" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


def test_removing_a_message_removes_its_photo_file(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", GroupMessage("t", "1", "U1", "Aki", "[写真]", image_file="1.jpg"))
    log.add("Cgroup", GroupMessage("t", "2", "U1", "Aki", "[写真]", image_file="2.jpg"))
    gone, kept = keep_photo(tmp_path, "1.jpg"), keep_photo(tmp_path, "2.jpg")
    log.remove("Cgroup", {"1"})
    assert not gone.exists() and kept.exists()


def test_a_photo_that_outlives_the_retention_period_is_removed_with_its_row(
    tmp_path: Path,
) -> None:
    log = GroupLog(tmp_path)
    log.add(
        "Cgroup",
        GroupMessage("2026-10-01T12:00:00+09:00", "1", "U1", "Aki", "[写真]", image_file="1.jpg"),
    )
    old = keep_photo(tmp_path, "1.jpg")
    cutoff = datetime.fromisoformat("2026-11-01T00:00:00+09:00")
    log.remove_older_than("Cgroup", cutoff, keep_since=None)
    assert not old.exists()


def test_removing_a_row_whose_photo_file_is_already_gone_is_fine(tmp_path: Path) -> None:
    log = GroupLog(tmp_path)
    log.add("Cgroup", GroupMessage("t", "1", "U1", "Aki", "[写真]", image_file="1.jpg"))
    assert [m.message_id for m in log.remove("Cgroup", {"1"})] == ["1"]
