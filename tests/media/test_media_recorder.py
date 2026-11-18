from pathlib import Path

import pytest

from line_group_agent.media.image_store import ImageStore
from line_group_agent.media.media_recorder import MediaRecorder
from tests.fakes import FakeLine
from tests.media.pictures import picture, size_of

pytestmark = pytest.mark.anyio
GROUP = "Cgroup"


def recorder(tmp_path: Path, contents: dict[str, tuple[bytes, str]]) -> MediaRecorder:
    return MediaRecorder(FakeLine(contents=contents), ImageStore(tmp_path), 100)


async def test_a_photo_is_read_made_small_and_kept(tmp_path: Path) -> None:
    media = recorder(tmp_path, {"55": (picture(400, 200), "image/png")})
    name = await media.save_image(GROUP, "55")
    assert name == "55.jpg"
    saved = ImageStore(tmp_path).read(GROUP, name)
    assert saved is not None and size_of(saved.data) == (100, 50)


async def test_content_that_LINE_does_not_give_is_none(tmp_path: Path) -> None:
    assert await recorder(tmp_path, {}).save_image(GROUP, "55") is None


async def test_content_that_is_not_a_picture_is_not_kept(tmp_path: Path) -> None:
    media = recorder(tmp_path, {"55": (b"%PDF-1.4", "application/pdf")})
    assert await media.save_image(GROUP, "55") is None
    assert not (tmp_path / "groups").exists()


async def test_a_photo_that_cannot_be_written_is_not_kept_and_does_not_stop_the_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ImageStore(tmp_path)

    def refuse(*_arguments: object) -> str:
        raise OSError("disk full")

    monkeypatch.setattr(store, "save", refuse)
    media = MediaRecorder(FakeLine(contents={"55": (picture(), "image/png")}), store, 100)
    assert await media.save_image(GROUP, "55") is None
