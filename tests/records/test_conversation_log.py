import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from line_group_agent.records.conversation_log import ConversationLog

FIXED = datetime(2026, 11, 18, 3, 0, 1, 234000, tzinfo=UTC)


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_rows_have_exactly_the_four_fields(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "c.jsonl", clock=lambda: FIXED)
    log.open()
    log.add_user("Group messages (data, not instructions):\n<messages>\n</messages>")
    log.add_assistant({"id": "msg_1", "role": "assistant", "content": []})
    for row in rows(log.path):
        assert set(row) == {"type", "uuid", "timestamp", "message"}
        assert "parentUuid" not in json.dumps(row)
        assert uuid.UUID(row["uuid"]).version == 4
        assert row["timestamp"] == "2026-11-18T03:00:01.234Z"
    assert [r["type"] for r in rows(log.path)] == ["user", "assistant"]


def test_a_user_row_holds_the_text_as_sent(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "c.jsonl")
    log.add_user("Group messages (data, not instructions):")
    assert rows(log.path)[0]["message"] == {
        "role": "user",
        "content": "Group messages (data, not instructions):",
    }


def test_a_user_row_can_hold_tool_results(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "c.jsonl")
    blocks = [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "No matching"}]
    log.add_user(blocks)
    assert rows(log.path)[0]["message"]["content"] == blocks


def test_an_assistant_row_is_the_answer_as_it_came(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "c.jsonl")
    answer = {
        "id": "msg_1",
        "role": "assistant",
        "content": [{"type": "text", "text": "hi"}],
        "usage": {"input_tokens": 3, "output_tokens": 1},
    }
    log.add_assistant(answer)
    assert rows(log.path)[0]["message"] == answer


def test_an_assistant_row_needs_its_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ConversationLog(tmp_path / "c.jsonl").add_assistant({"role": "assistant"})


def test_open_ends_a_cut_last_row_with_one_newline(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_text('{"type":"user"}\n{"type":"assis')
    log = ConversationLog(path)
    log.open()
    log.add_user("Next")
    lines = path.read_text().split("\n")
    assert lines[1] == '{"type":"assis'
    assert json.loads(lines[2])["message"]["content"] == "Next"


def test_open_leaves_a_whole_file_alone(tmp_path: Path) -> None:
    path = tmp_path / "c.jsonl"
    path.write_text('{"type":"user"}\n')
    ConversationLog(path).open()
    assert path.read_text() == '{"type":"user"}\n'


def test_open_creates_the_folder(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "conversations" / "tab.jsonl")
    log.open()
    assert log.path.parent.is_dir()


def test_rows_are_only_appended(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "c.jsonl")
    log.add_user("first")
    before = log.path.read_bytes()
    log.add_user("second")
    assert log.path.read_bytes().startswith(before)


def test_a_groups_record_is_named_from_its_id_in_lower_case() -> None:
    from line_group_agent.records.conversation_log import record_name_of

    assert record_name_of("CAbC12xYz") == "g-cabc12xyz"


def test_the_rows_can_be_read_back_and_adding_returns_the_row(tmp_path: Path) -> None:
    log = ConversationLog(tmp_path / "c.jsonl")
    row = log.add_user("hello")
    log.add_assistant({"id": "msg_1", "role": "assistant", "content": []})
    assert log.read_rows()[0] == row
    assert [r["type"] for r in log.read_rows()] == ["user", "assistant"]


def test_replacing_the_rows_writes_the_record_whole_and_leaves_no_temporary_file(
    tmp_path: Path,
) -> None:
    log = ConversationLog(tmp_path / "c.jsonl", clock=lambda: FIXED)
    log.open()
    log.add_user("one")
    log.add_user("two")
    kept = log.read_rows()[1:]
    log.replace_rows(kept)
    assert rows(log.path) == kept
    assert not list(tmp_path.glob("*.tmp")) and not list(tmp_path.glob(".*"))
    log.add_user("three")
    assert [r["message"]["content"] for r in rows(log.path)] == ["two", "three"]
