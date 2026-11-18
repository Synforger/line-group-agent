from pathlib import Path

import pytest

from line_group_agent.media.image_shrinker import StoredImage
from line_group_agent.media.image_store import ImageStore

GROUP = "Cgroup"
PNG = StoredImage(b"png bytes", "image/png")


def test_a_photo_is_saved_under_the_group_and_read_back(tmp_path: Path) -> None:
    store = ImageStore(tmp_path)
    name = store.save(GROUP, "4455", PNG)
    assert name == "4455.png"
    assert (tmp_path / "groups" / GROUP / "images" / "4455.png").read_bytes() == b"png bytes"
    assert store.read(GROUP, name) == PNG


def test_the_extension_follows_the_media_type(tmp_path: Path) -> None:
    store = ImageStore(tmp_path)
    assert store.save(GROUP, "1", StoredImage(b"x", "image/jpeg")) == "1.jpg"
    assert store.save(GROUP, "2", StoredImage(b"x", "image/webp")) == "2.webp"


def test_a_message_id_cannot_leave_the_folder(tmp_path: Path) -> None:
    name = ImageStore(tmp_path).save(GROUP, "../../etc/x", PNG)
    assert "/" not in name and "." not in name.removesuffix(".png")
    assert [p.parent for p in tmp_path.rglob(name)] == [tmp_path / "groups" / GROUP / "images"]


def test_reading_a_missing_or_foreign_file_gives_none(tmp_path: Path) -> None:
    store = ImageStore(tmp_path)
    assert store.read(GROUP, "9.png") is None
    assert store.read(GROUP, "notes.txt") is None
    assert store.read(GROUP, "../../x.png") is None


def test_a_group_id_that_is_not_letters_and_digits_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="group id"):
        ImageStore(tmp_path).save("../x", "1", PNG)
