from line_group_agent.simulator.message_actions import action_numbers, list_actions

VOTE = {"type": "postback", "label": "A", "data": "poll:p1:0"}
OPEN = {"type": "uri", "label": "Open", "uri": "https://example.com"}
HERO = {"type": "uri", "uri": "https://example.com/hero"}
QUICK = {"type": "message", "label": "Yes", "text": "yes"}
FLEX = {
    "type": "flex",
    "altText": "x",
    "contents": {
        "type": "bubble",
        "body": {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "action": VOTE},
            {"type": "text", "text": "no action here"},
        ]},
        "footer": {"type": "box", "layout": "vertical", "contents": [
            {"type": "button", "action": OPEN},
        ]},
        "hero": {"type": "image", "url": "https://example.com/a.png", "action": HERO},
    },
    "quickReply": {"items": [{"type": "action", "action": QUICK}]},
}  # fmt: skip


def test_actions_come_in_the_order_they_are_drawn_then_the_quick_replies() -> None:
    # The JSON lists the hero last, but a bubble draws it first.
    assert list_actions([FLEX]) == [HERO, VOTE, OPEN, QUICK]


def test_several_messages_are_counted_one_after_the_other() -> None:
    text = {"type": "text", "text": "hi", "quickReply": {"items": [{"action": QUICK}]}}
    assert list_actions([text, FLEX]) == [QUICK, HERO, VOTE, OPEN, QUICK]


def test_a_message_without_actions_gives_none() -> None:
    assert list_actions([{"type": "text", "text": "hi"}]) == []
    assert list_actions([]) == []


def test_the_numbers_follow_the_same_order_by_object() -> None:
    numbers = action_numbers([FLEX])
    assert [numbers[id(action)] for action in (HERO, VOTE, OPEN, QUICK)] == [0, 1, 2, 3]
