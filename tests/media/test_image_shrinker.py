import io

import pytest
from PIL import Image

from line_group_agent.media import image_shrinker
from line_group_agent.media.image_shrinker import shrink_image
from tests.media.pictures import grainy, picture, size_of


def test_a_small_picture_is_kept_as_it_is() -> None:
    data = picture(40, 30)
    stored = shrink_image(data, 100)
    assert stored is not None and stored.data == data and stored.media_type == "image/png"


@pytest.mark.parametrize(
    ("image_format", "media_type"),
    [("JPEG", "image/jpeg"), ("GIF", "image/gif"), ("WEBP", "image/webp")],
)
def test_the_other_formats_the_api_takes_are_kept_too(image_format: str, media_type: str) -> None:
    stored = shrink_image(picture(image_format=image_format), 100)
    assert stored is not None and stored.media_type == media_type


def test_a_picture_longer_than_the_limit_is_scaled_down_to_a_jpeg() -> None:
    stored = shrink_image(picture(400, 200), 100)
    assert stored is not None and stored.media_type == "image/jpeg"
    assert size_of(stored.data) == (100, 50)


def test_a_tall_picture_is_limited_on_its_long_side() -> None:
    stored = shrink_image(picture(200, 400), 100)
    assert stored is not None and size_of(stored.data) == (50, 100)


def test_transparent_parts_become_white_when_a_picture_is_saved_again() -> None:
    stored = shrink_image(picture(400, 200, mode="RGBA"), 100)
    assert stored is not None
    with Image.open(io.BytesIO(stored.data)) as image:
        red, green, blue = image.convert("RGB").getpixel((10, 10))
    assert min(red, green, blue) > 240


def test_a_picture_over_the_byte_limit_is_saved_again_even_if_its_size_fits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data = grainy(200, 200)
    monkeypatch.setattr(image_shrinker, "MAX_IMAGE_BYTES", len(data) - 1)
    stored = shrink_image(data, 1000)
    assert stored is not None and stored.media_type == "image/jpeg"
    assert size_of(stored.data) == (200, 200) and len(stored.data) < len(data)


def test_a_picture_that_stays_over_the_byte_limit_gives_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(image_shrinker, "MAX_IMAGE_BYTES", 10)
    assert shrink_image(picture(400, 200), 100) is None


@pytest.mark.parametrize("data", [b"", b"not a picture", picture(image_format="BMP")])
def test_something_that_is_not_a_usable_picture_gives_nothing(data: bytes) -> None:
    assert shrink_image(data, 100) is None


def test_a_picture_cut_short_gives_nothing() -> None:
    data = picture(300, 300, image_format="JPEG")
    assert shrink_image(data[: len(data) // 2], 1000) is None
