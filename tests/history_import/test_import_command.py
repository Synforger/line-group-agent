import json
from pathlib import Path

import pytest

from line_group_agent.__main__ import main
from line_group_agent.records.group_log import GroupLog
from tests.fakes import raw_config

GROUP = "Cgroup"
HISTORY = "2026/09/01\n10:00\tAki\tfirst\n10:01\tSora\tsecond\nnot understood\n"


def setup(tmp_path: Path) -> tuple[Path, Path]:
    config = tmp_path / "config.json"
    config.write_text(json.dumps(raw_config(tmp_path)))
    history = tmp_path / "history.txt"
    history.write_text(HISTORY, encoding="utf-8")
    return config, history


def run(config: Path, history: Path, group: str = GROUP) -> int:
    return main(["import-history", "--config", str(config), "--group", group, str(history)])


def test_the_command_adds_the_messages_and_says_what_it_did(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, history = setup(tmp_path)
    assert run(config, history) == 0
    assert capsys.readouterr().out == (
        "added 2 message(s); 0 already in the record; 0 notice line(s) skipped; "
        "1 line(s) not understood\n"
    )
    log = GroupLog(tmp_path / "state")
    assert [m.text for m in log.list_recent(GROUP, 10)] == ["first", "second"]


def test_running_it_again_adds_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config, history = setup(tmp_path)
    run(config, history)
    capsys.readouterr()
    assert run(config, history) == 0
    assert capsys.readouterr().out.startswith("added 0 message(s); 2 already in the record")


def test_a_file_that_starts_with_a_byte_order_mark_is_read(tmp_path: Path) -> None:
    config, history = setup(tmp_path)
    history.write_bytes(b"\xef\xbb\xbf" + HISTORY.encode())
    assert run(config, history) == 0
    assert len(GroupLog(tmp_path / "state").list_recent(GROUP, 10)) == 2


def test_a_file_in_another_encoding_does_not_stop_the_command(tmp_path: Path) -> None:
    config, history = setup(tmp_path)
    history.write_bytes("2026/09/01\n10:00\tAki\tこんにちは\n".encode("shift_jis"))
    assert run(config, history) == 0


@pytest.mark.parametrize("group", ["../x", "", "C group"])
def test_a_group_id_that_is_not_letters_and_digits_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], group: str
) -> None:
    config, history = setup(tmp_path)
    assert run(config, history, group) == 2
    assert "group id" in capsys.readouterr().err


def test_a_missing_file_or_configuration_is_a_mistake_not_a_crash(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config, history = setup(tmp_path)
    assert run(config, tmp_path / "missing.txt") == 2
    assert run(tmp_path / "missing.json", history) == 2
    assert capsys.readouterr().err.count("import-history") == 2
    assert not (tmp_path / "state").exists()
