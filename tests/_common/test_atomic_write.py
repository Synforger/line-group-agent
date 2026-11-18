from pathlib import Path

from line_group_agent._common.atomic_write import write_text_atomically


def test_the_file_is_replaced_whole_and_no_temporary_is_left(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "file.json"
    write_text_atomically(path, "one")
    write_text_atomically(path, "two")
    assert path.read_text() == "two"
    assert [p.name for p in path.parent.iterdir()] == ["file.json"]
