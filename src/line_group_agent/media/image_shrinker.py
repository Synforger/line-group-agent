"""Make a photo a member sent small enough to give to the model.

A photo whose long side is within the configured size and whose file is under the API's
limit is kept as it is. A larger one is scaled down and saved again as JPEG. Something that
is not a JPEG, PNG, GIF or WEBP image (or cannot be decoded) gives nothing, so a broken
file never ends up in the conversation, where it would make every later request fail.

Needs no network and no files; called by the media recorder.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps

JPEG_TYPE = "image/jpeg"
FORMAT_TYPES = {
    "JPEG": JPEG_TYPE,
    "PNG": "image/png",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}
# The API takes an image up to 5 MB; this leaves room for the base64 form's overhead.
MAX_IMAGE_BYTES = 4_500_000
JPEG_QUALITIES = (85, 70, 55)
WHITE = (255, 255, 255)


@dataclass(frozen=True)
class StoredImage:
    """An image ready to keep: its bytes and its media type (`image/jpeg` and so on)."""

    data: bytes
    media_type: str


def shrink_image(data: bytes, max_edge_pixels: int) -> StoredImage | None:
    """Return the image within `max_edge_pixels` on its long side and `MAX_IMAGE_BYTES`, or
    None when `data` is not an image the model can be given."""
    try:
        with Image.open(io.BytesIO(data)) as image:
            media_type = FORMAT_TYPES.get(image.format or "")
            if media_type is None:
                return None
            image.load()
            if max(image.size) <= max_edge_pixels and len(data) <= MAX_IMAGE_BYTES:
                return StoredImage(data, media_type)
            return _as_small_jpeg(image, max_edge_pixels)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _as_small_jpeg(image: Image.Image, max_edge_pixels: int) -> StoredImage | None:
    upright = ImageOps.exif_transpose(image)
    upright.thumbnail((max_edge_pixels, max_edge_pixels), Image.Resampling.LANCZOS)
    flat = _on_white(upright)
    for quality in JPEG_QUALITIES:
        buffer = io.BytesIO()
        flat.save(buffer, format="JPEG", quality=quality)
        if buffer.tell() <= MAX_IMAGE_BYTES:
            return StoredImage(buffer.getvalue(), JPEG_TYPE)
    return None


def _on_white(image: Image.Image) -> Image.Image:
    """Return the image as RGB; transparent parts become white (JPEG has no transparency)."""
    rgba = image.convert("RGBA")
    background = Image.new("RGB", rgba.size, WHITE)
    background.paste(rgba, mask=rgba.getchannel("A"))
    return background
