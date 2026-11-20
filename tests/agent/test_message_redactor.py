from typing import Any

from line_group_agent.agent.message_redactor import redact_row
from line_group_agent.agent.prompt import build_envelope, format_search_results
from line_group_agent.records.group_log import GroupMessage

SECRET = GroupMessage("2026-11-18T12:00:01+09:00", "m1", "U1", "Aki", "the <secret> plan & more")
OTHER = GroupMessage("2026-11-18T12:00:02+09:00", "m2", "U2", "Bo", "lunch?")
MENTION = GroupMessage("2026-11-18T12:00:03+09:00", "m3", "U1", "Aki", "@bot hi")
BOT = GroupMessage("2026-11-18T12:00:04+09:00", "bot-1", None, None, "Try Gion Inn.", True)


def user_row(content: Any) -> dict[str, Any]:
    return {
        "type": "user",
        "uuid": "u",
        "timestamp": "t",
        "message": {"role": "user", "content": content},
    }


def assistant_row(content: list[dict[str, Any]]) -> dict[str, Any]:
    message = {"id": "msg_1", "role": "assistant", "content": content, "usage": {"input_tokens": 9}}
    return {"type": "assistant", "uuid": "a", "timestamp": "t", "message": message}


def test_a_deleted_message_in_the_envelope_says_deleted_and_the_others_stay() -> None:
    row = user_row(build_envelope([SECRET, OTHER], MENTION))
    text = redact_row(row, [SECRET])["message"]["content"]
    assert "secret" not in text and "&lt;" not in text
    assert 'from="Aki">[deleted]</message>' in text or "from='Aki'>[deleted]</message>" in text
    assert "lunch?" in text and "@bot hi" in text


def test_a_deleted_mention_and_a_deleted_bot_reply_are_marked_in_the_envelope() -> None:
    row = user_row(build_envelope([BOT, OTHER], SECRET))
    text = redact_row(row, [SECRET, BOT])["message"]["content"]
    assert "Gion Inn" not in text and "secret" not in text
    assert "<your_reply" in text and "[deleted]</your_reply>" in text
    assert "[deleted]</mention>" in text


def test_a_search_result_line_of_a_deleted_message_is_marked_inside_a_tool_result() -> None:
    results = format_search_results([OTHER, SECRET])
    block = {"type": "tool_result", "tool_use_id": "t1", "content": results}
    changed = redact_row(user_row([block]), [SECRET])["message"]["content"][0]
    assert "secret" not in changed["content"] and "lunch?" in changed["content"]
    assert changed["tool_use_id"] == "t1"


def test_text_blocks_and_nested_tool_result_blocks_of_a_user_row_are_covered() -> None:
    nested = {
        "type": "tool_result",
        "tool_use_id": "t",
        "content": [{"type": "text", "text": build_envelope([SECRET], MENTION)}],
    }
    blocks = [nested, {"type": "text", "text": build_envelope([SECRET], MENTION)}]
    changed = redact_row(user_row(blocks), [SECRET])["message"]["content"]
    assert "secret" not in str(changed)


def test_thinking_blocks_are_dropped_from_answers_and_other_blocks_stay() -> None:
    blocks = [
        {"type": "thinking", "thinking": "the secret plan", "signature": "s"},
        {"type": "redacted_thinking", "data": "x"},
        {"type": "text", "text": "<reply>Hi</reply>"},
    ]
    changed = redact_row(assistant_row(blocks), [SECRET])["message"]
    assert changed["content"] == [{"type": "text", "text": "<reply>Hi</reply>"}]
    assert changed["usage"] == {"input_tokens": 9} and changed["id"] == "msg_1"


def test_an_answer_of_only_thinking_keeps_its_blocks_rather_than_becoming_empty() -> None:
    blocks = [{"type": "thinking", "thinking": "hm", "signature": "s"}]
    assert redact_row(assistant_row(blocks), [])["message"]["content"] == blocks


def test_a_deleted_bot_reply_is_marked_inside_its_reply_tags_even_when_it_was_markdown() -> None:
    reply = GroupMessage(
        "t", "bot-2", None, None, "Hotels\n・Gion Inn\n[カード] 1. Gion https://e.com", True
    )
    blocks = [{"type": "text", "text": "ok <reply># Hotels\n- **Gion Inn**</reply> bye"}]
    changed = redact_row(assistant_row(blocks), [reply])["message"]["content"]
    assert changed == [{"type": "text", "text": "ok <reply>[deleted]</reply> bye"}]


def test_another_reply_of_the_bot_is_left_alone() -> None:
    blocks = [{"type": "text", "text": "<reply>Something else.</reply>"}]
    assert redact_row(assistant_row(blocks), [BOT])["message"]["content"] == blocks


def test_a_deleted_members_message_is_not_searched_for_in_answers() -> None:
    blocks = [{"type": "text", "text": "<reply>You said the <secret> plan & more</reply>"}]
    assert redact_row(assistant_row(blocks), [SECRET])["message"]["content"] == blocks


def test_a_row_without_a_message_is_returned_as_it_is() -> None:
    row = {"type": "user", "uuid": "u", "timestamp": "t", "message": "odd"}
    assert redact_row(row, [SECRET]) == row


def test_a_bot_reply_that_carried_a_poll_and_a_place_is_still_found() -> None:
    reply = GroupMessage(
        "t",
        "bot-3",
        None,
        None,
        "Vote below.\n[投票] p1 Where? 1. Kyoto / 2. Osaka\n[位置] Gion Inn Kyoto (35.0, 135.0)",
        True,
    )
    blocks = [{"type": "text", "text": "<reply>Vote below.</reply>"}]
    changed = redact_row(assistant_row(blocks), [reply])["message"]["content"]
    assert changed == [{"type": "text", "text": "<reply>[deleted]</reply>"}]


def test_a_bot_reply_that_carried_a_sticker_is_still_found() -> None:
    reply = GroupMessage("t", "bot-5", None, None, "Thanks!\n(スタンプ: ありがとう)", True)
    blocks = [{"type": "text", "text": "<reply>Thanks!</reply>"}]
    changed = redact_row(assistant_row(blocks), [reply])["message"]["content"]
    assert changed == [{"type": "text", "text": "<reply>[deleted]</reply>"}]


def test_a_reply_that_only_starts_the_same_way_is_not_taken_for_the_deleted_one() -> None:
    reply = GroupMessage("t", "bot-4", None, None, "Vote below.\nand then more words", True)
    blocks = [{"type": "text", "text": "<reply>Vote below.</reply>"}]
    assert redact_row(assistant_row(blocks), [reply])["message"]["content"] == blocks


def test_the_caption_and_image_of_a_deleted_photo_become_one_deleted_text() -> None:
    from line_group_agent.agent.prompt import photo_caption

    photo = GroupMessage("t", "m7", "U1", "Aki", "[写真]", image_file="m7.jpg")
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": "A"}}
    other = GroupMessage("t2", "m8", "U1", "Aki", "[写真]", image_file="m8.jpg")
    content = [
        {"type": "text", "text": "envelope"},
        {"type": "text", "text": photo_caption(photo)},
        image,
        {"type": "text", "text": photo_caption(other)},
        image,
    ]
    changed = redact_row(user_row(content), [photo])["message"]["content"]
    assert changed == [
        {"type": "text", "text": "envelope"},
        {"type": "text", "text": "[deleted]"},
        {"type": "text", "text": photo_caption(other)},
        image,
    ]
