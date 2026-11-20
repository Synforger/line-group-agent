from typing import Any

from line_group_agent.simulator.chat_page import render_chat_page
from line_group_agent.simulator.transcript import (
    OutputRecord,
    ScenarioTranscript,
    SpendFigure,
    StepRecord,
)

SPEND = SpendFigure(0.5, 0.0033, "JPY")
NOTHING = SpendFigure(0.0, 0.0, "JPY")
GROUP = {"id": "Cg", "name": "Trip friends", "members": [{"user_id": "Ua", "name": "Aki"}]}


def step(index: int, kind: str, shown: dict[str, Any] | None, **fields: Any) -> StepRecord:
    values: dict[str, Any] = {
        "index": index,
        "kind": kind,
        "sender": "Ua",
        "sender_name": "Aki",
        "input": {},
        "shown": shown,
        "event": None,
        "outputs": [],
        "seconds": 1.5,
        "first_output_seconds": None,
        "spend": NOTHING,
    }
    values.update(fields)
    return StepRecord(**values)


def page_of(*steps: StepRecord) -> str:
    transcript = ScenarioTranscript(
        "trip", "A trip", GROUP, "Sora", "2026-11-20T10:00:00+09:00", list(steps)
    )
    return render_chat_page(transcript, {"/tmp/menu.png": "data:image/jpeg;base64,AAAA"})


def test_members_and_the_bot_are_drawn_with_names_and_the_step_numbers() -> None:
    reply = OutputRecord(0, "reply", 1.2, "token", [{"type": "text", "text": "Hi Aki!"}])
    html = page_of(
        step(
            0,
            "text",
            {"type": "text", "text": "@Sora hello"},
            outputs=[reply],
            first_output_seconds=1.2,
            spend=SPEND,
        )
    )
    assert "Trip friends" in html and "2026-11-20" in html
    assert ">Aki<" in html and "@Sora hello" in html and "Hi Aki!" in html
    assert "Sora · reply #0" in html
    assert "step 0 · first 1.2s · 1.5s · 0.5 JPY ($0.0033)" in html


def test_a_step_the_bot_stayed_silent_on_says_so() -> None:
    html = page_of(step(0, "text", {"type": "text", "text": "just chatting"}))
    assert "no reply" in html


def test_the_quoted_message_shows_above_the_bot_text() -> None:
    asked = step(
        0,
        "text",
        {"type": "text", "text": "where?"},
        event={"message": {"quoteToken": "q1", "text": "where?"}},
    )
    said = OutputRecord(
        0, "reply", 1.0, "t", [{"type": "text", "text": "Kyoto", "quoteToken": "q1"}]
    )
    html = page_of(asked, step(1, "text", {"type": "text", "text": "ok"}, outputs=[said]))
    assert '<span class="quote">where?</span>' in html


def test_quick_reply_buttons_are_chips_with_their_numbers() -> None:
    message = {
        "type": "text",
        "text": "pick",
        "quickReply": {
            "items": [
                {"type": "action", "action": {"type": "message", "label": "Yes", "text": "y"}}
            ]
        },
    }
    html = page_of(
        step(
            0,
            "text",
            {"type": "text", "text": "q"},
            outputs=[OutputRecord(0, "reply", 1, "t", [message])],
        )
    )
    assert '<span class="chip">Yes<sup>#0</sup></span>' in html


def test_photos_pins_presses_waits_and_opened_pages_are_drawn() -> None:
    html = page_of(
        step(0, "image", {"type": "image", "file": "/tmp/menu.png"}),
        step(
            1,
            "location",
            {
                "type": "location",
                "title": "Cafe",
                "address": "Kyoto",
                "latitude": 35,
                "longitude": 135,
            },
        ),
        step(2, "press", {"type": "press", "label": "Kyoto", "display_text": "Kyoto に投票"}),
        step(3, "press", {"type": "press", "label": "Open", "display_text": None}),
        step(4, "wait", {"type": "wait", "seconds": 2}),
        step(5, "open_liff", {"type": "open_liff", "url": "u"}, screen="screens/step-05-liff.png"),
    )
    assert 'src="data:image/jpeg;base64,AAAA"' in html
    assert "<b>Cafe</b>" in html and "35, 135" in html
    assert "Kyoto に投票" in html and "pressed 「Open」" in html
    assert '<div class="pass">2 s</div>' in html
    assert 'src="screens/step-05-liff.png"' in html and "opened the page" in html


def test_a_problem_is_shown_and_everything_is_escaped() -> None:
    html = page_of(
        step(0, "text", {"type": "text", "text": "<b>x</b>"}, error="the bot was not done <soon>")
    )
    assert "⚠ the bot was not done &lt;soon&gt;" in html
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_the_page_loads_nothing_from_outside() -> None:
    html = page_of(step(0, "text", {"type": "text", "text": "hi"}))
    assert "http://" not in html and "https://" not in html
    assert "<script" not in html
