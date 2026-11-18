import base64
from pathlib import Path

from line_group_agent.media.image_shrinker import StoredImage
from line_group_agent.media.image_store import ImageStore
from line_group_agent.media.photo_picker import PhotoPicker
from line_group_agent.records.group_log import GroupMessage

GROUP = "Cgroup"


def photo_message(number: int, *, from_bot: bool = False, file: str | None = "") -> GroupMessage:
    name = f"{number}.png" if file == "" else file
    return GroupMessage(f"t{number}", str(number), "U1", "Aki", "[写真]", from_bot, name)


def stored(tmp_path: Path, numbers: list[int]) -> ImageStore:
    store = ImageStore(tmp_path)
    for number in numbers:
        store.save(GROUP, str(number), StoredImage(f"data {number}".encode(), "image/png"))
    return store


def test_the_newest_photos_up_to_the_limit_come_back_oldest_first(tmp_path: Path) -> None:
    picker = PhotoPicker(stored(tmp_path, [1, 2, 3, 4]), 3)
    photos = picker.pick(GROUP, [photo_message(n) for n in (1, 2, 3, 4)])
    assert [p.message.message_id for p in photos] == ["2", "3", "4"]
    assert photos[0].media_type == "image/png"
    assert base64.b64decode(photos[0].data) == b"data 2"


def test_messages_without_a_photo_and_the_bots_own_are_skipped(tmp_path: Path) -> None:
    picker = PhotoPicker(stored(tmp_path, [1, 2]), 3)
    text = GroupMessage("t", "9", "U1", "Aki", "hello")
    photos = picker.pick(GROUP, [text, photo_message(1, from_bot=True), photo_message(2)])
    assert [p.message.message_id for p in photos] == ["2"]


def test_a_photo_whose_file_is_gone_is_left_out_and_does_not_use_up_the_limit(
    tmp_path: Path,
) -> None:
    picker = PhotoPicker(stored(tmp_path, [1, 3]), 2)
    photos = picker.pick(GROUP, [photo_message(n) for n in (1, 2, 3)])
    assert [p.message.message_id for p in photos] == ["3"]


def test_a_limit_of_zero_shows_no_photos(tmp_path: Path) -> None:
    picker = PhotoPicker(stored(tmp_path, [1]), 0)
    assert picker.pick(GROUP, [photo_message(1)]) == []
