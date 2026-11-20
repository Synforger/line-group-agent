import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from line_group_agent.itinerary.itinerary_image_store import (
    IMAGE_FOLDER_NAME,
    IMAGE_KEEP_DAYS,
    ItineraryImageStore,
)

NOW = datetime(2026, 11, 23, 8, 0, tzinfo=timezone(timedelta(hours=9)))
PNG = b"\x89PNG\r\n\x1a\nfake"


def store_at(tmp_path: Path) -> ItineraryImageStore:
    return ItineraryImageStore(tmp_path, lambda: NOW)


def age(file: Path, days: float) -> None:
    moment = (NOW - timedelta(days=days)).timestamp()
    os.utime(file, (moment, moment))


def test_a_saved_image_lives_in_the_groups_folder_under_an_unguessable_name(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path)
    name = store.save("Cgroup", PNG)
    assert (tmp_path / "groups" / "Cgroup" / IMAGE_FOLDER_NAME / name).read_bytes() == PNG
    assert len(name) == 22 + len(".png") and name.endswith(".png")
    assert store.save("Cgroup", PNG) != name


def test_an_image_is_read_by_its_name_whichever_group_it_belongs_to(tmp_path: Path) -> None:
    store = store_at(tmp_path)
    first = store.save("Cone", PNG)
    second = store.save("Ctwo", PNG + b"2")
    assert store.read(first) == PNG
    assert store.read(second) == PNG + b"2"


@pytest.mark.parametrize(
    "name", ["", "x.png", "../../etc/passwd", "a" * 22 + ".jpg", "a" * 22, "a/" + "b" * 20 + ".png"]
)
def test_a_name_that_is_not_one_the_store_made_reads_nothing(tmp_path: Path, name: str) -> None:
    store = store_at(tmp_path)
    store.save("Cgroup", PNG)
    assert store.read(name) is None


def test_an_unknown_name_reads_nothing(tmp_path: Path) -> None:
    assert store_at(tmp_path).read("a" * 22 + ".png") is None


def test_an_image_past_its_keeping_time_is_not_served_and_is_removed_by_the_next_save(
    tmp_path: Path,
) -> None:
    store = store_at(tmp_path)
    old = store.save("Cgroup", PNG)
    recent = store.save("Cgroup", PNG)
    folder = tmp_path / "groups" / "Cgroup" / IMAGE_FOLDER_NAME
    age(folder / old, IMAGE_KEEP_DAYS + 1)
    age(folder / recent, IMAGE_KEEP_DAYS - 1)
    assert store.read(old) is None and store.read(recent) == PNG
    store.save("Cgroup", PNG)
    assert not (folder / old).exists() and (folder / recent).exists()


def test_a_group_id_that_is_not_letters_and_digits_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        store_at(tmp_path).save("../x", PNG)
