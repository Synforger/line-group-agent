"""A sticker the bot may send: the name the model asks for it by, and LINE's ids for it.

Plain value; held by the configuration, read by the sticker tool.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sticker:
    """`name` is what the model picks (and the group's record shows); `package_id` and
    `sticker_id` are LINE's ids of the sticker."""

    name: str
    package_id: str
    sticker_id: str
