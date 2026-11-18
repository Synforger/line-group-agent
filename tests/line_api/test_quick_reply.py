from line_group_agent.line_api.quick_reply import (
    MAX_QUICK_REPLY_COUNT,
    QuickReplyItem,
    build_quick_reply,
)


def test_each_item_becomes_a_message_action_button() -> None:
    built = build_quick_reply([QuickReplyItem("Kyoto", "Sora、Kyoto")])
    assert built == {
        "items": [
            {
                "type": "action",
                "action": {"type": "message", "label": "Kyoto", "text": "Sora、Kyoto"},
            }
        ]
    }


def test_only_the_first_thirteen_items_are_kept() -> None:
    items = [QuickReplyItem(str(n), str(n)) for n in range(20)]
    assert len(build_quick_reply(items)["items"]) == MAX_QUICK_REPLY_COUNT
