from pathlib import Path

from line_group_agent._common.atomic_write import write_text_atomically


def test_the_file_is_replaced_whole_and_no_temporary_is_left(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "file.json"
    write_text_atomically(path, "one")
    write_text_atomically(path, "two")
    assert path.read_text() == "two"
    assert [p.name for p in path.parent.iterdir()] == ["file.json"]


def test_bytes_are_written_whole_and_leave_no_temporary_file(tmp_path: Path) -> None:
    from line_group_agent._common.atomic_write import write_bytes_atomically

    target = tmp_path / "images" / "1.png"
    write_bytes_atomically(target, b"\x89PNG")
    write_bytes_atomically(target, b"\x89PNG again")
    assert target.read_bytes() == b"\x89PNG again"
    assert [p.name for p in target.parent.iterdir()] == ["1.png"]
