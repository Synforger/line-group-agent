"""Small pictures made in memory for the photo tests."""

from __future__ import annotations

import io

from PIL import Image


def picture(
    width: int = 40, height: int = 30, *, image_format: str = "PNG", mode: str = "RGB"
) -> bytes:
    """Return the bytes of a plain picture in the given format."""
    color = (200, 30, 30, 0) if mode == "RGBA" else (200, 30, 30)
    buffer = io.BytesIO()
    Image.new(mode, (width, height), color).save(buffer, format=image_format)
    return buffer.getvalue()


def size_of(data: bytes) -> tuple[int, int]:
    """Return the width and height of the picture in `data`."""
    with Image.open(io.BytesIO(data)) as image:
        return image.size


def grainy(width: int = 200, height: int = 200) -> bytes:
    """Return the bytes of a noisy PNG, which is several times smaller as a JPEG."""
    buffer = io.BytesIO()
    Image.effect_noise((width, height), 12).convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()
