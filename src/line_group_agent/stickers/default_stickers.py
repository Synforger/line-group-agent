"""The stickers the bot may send when the configuration does not give its own list.

All are among the stickers LINE lets a bot send (the "sticker list" page of the Messaging API
documentation): packages 8515 and 11537, which are made of everyday phrases. Plain values;
read by the configuration.
"""

from __future__ import annotations

from line_group_agent.stickers.sticker import Sticker

DEFAULT_STICKERS: tuple[Sticker, ...] = (
    Sticker("了解", "8515", "16581242"),
    Sticker("ありがとう", "8515", "16581243"),
    Sticker("おめでとう", "11537", "52002734"),
    Sticker("ごめん", "8515", "16581250"),
    Sticker("笑う", "11537", "52002748"),
    Sticker("楽しみ", "8515", "16581251"),
    Sticker("おやすみ", "8515", "16581261"),
    Sticker("よろしく", "8515", "16581248"),
    Sticker("びっくり", "11537", "52002749"),
    Sticker("がんばれ", "8515", "16581265"),
    Sticker("おつかれさま", "8515", "16581252"),
)
