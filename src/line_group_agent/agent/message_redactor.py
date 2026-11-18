"""Take deleted messages out of the rows of a conversation record.

A row shows a message in a few known shapes: an element of the envelope, a line of a
history-search result, a photo (its caption and image block) and, for the bot's own
replies, a `<reply>` in an answer. Each is rewritten to say `[deleted]` instead of the text.
Thinking blocks are dropped from answers, since they can no longer be sent back once what
came before them changed.
What the model wrote about a member's message in its own words is not found.

Pure functions; called by the message deleter for every row of a record.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from line_group_agent.agent.plain_text import to_plain_text
from line_group_agent.agent.prompt import (
    DELETED_MARK,
    REPLY_PATTERN,
    format_search_results,
    message_element,
    photo_caption,
)
from line_group_agent.cards.card_record import CARD_RECORD_LABEL
from line_group_agent.records.group_log import GroupMessage

THINKING_BLOCK_TYPES = ("thinking", "redacted_thinking")
ELEMENT_TAGS = ("message", "mention")


def redact_row(row: dict[str, Any], deleted: Sequence[GroupMessage]) -> dict[str, Any]:
    """Return the row of a conversation record without the `deleted` messages."""
    message = row.get("message")
    if not isinstance(message, dict):
        return row
    content = message.get("content")
    if row.get("type") == "user":
        content = _redact_user_content(content, deleted)
    elif row.get("type") == "assistant":
        content = _redact_answer_content(content, [m for m in deleted if m.from_bot])
    return {**row, "message": {**message, "content": content}}


def _redact_user_content(content: Any, deleted: Sequence[GroupMessage]) -> Any:
    if isinstance(content, str):
        return _redact_text(content, deleted)
    if not isinstance(content, list):
        return content
    return [_redact_user_block(block, deleted) for block in _redact_photos(content, deleted)]


def _redact_photos(blocks: list[Any], deleted: Sequence[GroupMessage]) -> list[Any]:
    """Replace the caption and the image block of each deleted photo by one `[deleted]` text."""
    captions = {photo_caption(message) for message in deleted if message.image_file}
    if not captions:
        return blocks
    kept: list[Any] = []
    skip_image = False
    for index, block in enumerate(blocks):
        if skip_image:
            skip_image = False
            continue
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        if _is_text(block) and block["text"] in captions and _is_image(following):
            kept.append({"type": "text", "text": DELETED_MARK})
            skip_image = True
            continue
        kept.append(block)
    return kept


def _is_text(block: Any) -> bool:
    return (
        isinstance(block, dict)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


def _is_image(block: Any) -> bool:
    return isinstance(block, dict) and block.get("type") == "image"


def _redact_user_block(block: Any, deleted: Sequence[GroupMessage]) -> Any:
    if not isinstance(block, dict):
        return block
    if block.get("type") == "text" and isinstance(block.get("text"), str):
        return {**block, "text": _redact_text(block["text"], deleted)}
    if block.get("type") == "tool_result":
        return {**block, "content": _redact_user_content(block.get("content"), deleted)}
    return block


def _redact_text(text: str, deleted: Sequence[GroupMessage]) -> str:
    for message in deleted:
        marked = replace(message, text=DELETED_MARK)
        for tag in ELEMENT_TAGS:
            text = text.replace(message_element(tag, message), message_element(tag, marked))
        text = text.replace(format_search_results([message]), format_search_results([marked]))
    return text


def _redact_answer_content(content: Any, deleted_replies: Sequence[GroupMessage]) -> Any:
    if not isinstance(content, list):
        return content
    kept = [b for b in content if not _is_thinking(b)]
    blocks = kept or content
    return [_redact_answer_block(block, deleted_replies) for block in blocks]


def _redact_answer_block(block: Any, deleted_replies: Sequence[GroupMessage]) -> Any:
    if not deleted_replies or not isinstance(block, dict):
        return block
    if block.get("type") != "text" or not isinstance(block.get("text"), str):
        return block

    def mark_if_deleted(found: Any) -> str:
        if any(_is_reply_of(found.group(1), message) for message in deleted_replies):
            return f"<reply>{DELETED_MARK}</reply>"
        return str(found.group(0))

    return {**block, "text": REPLY_PATTERN.sub(mark_if_deleted, block["text"])}


def _is_thinking(block: Any) -> bool:
    return isinstance(block, dict) and block.get("type") in THINKING_BLOCK_TYPES


def _is_reply_of(body: str, message: GroupMessage) -> bool:
    """Whether the record's text for a bot message is this reply (made plain, and
    followed by the line that names its cards when it had any)."""
    plain = to_plain_text(body.strip())
    if not plain:
        return False
    return message.text == plain or message.text.startswith(f"{plain}\n{CARD_RECORD_LABEL}")
