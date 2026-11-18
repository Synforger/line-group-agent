import logging

import pytest

from line_group_agent.agent.answerer import Answer
from line_group_agent.cards.card import Card
from line_group_agent.events.answer_sender import AnswerSender
from line_group_agent.line_api.line_client import LineApiError, ReplyResult
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem
from tests.fakes import FakeLine

pytestmark = pytest.mark.anyio
GROUP = "Callowed"
TOKEN = "reply-token-1"
CARDS = [Card("Gion Inn", "x", "https://example.com/1", image_url="https://e.com/1.jpg")]
BOTH = Answer("Two options.", CARDS)


async def test_text_and_cards_go_out_in_one_reply() -> None:
    line = FakeLine()
    sent = await AnswerSender(line).send(GROUP, TOKEN, BOTH)
    assert sent == BOTH
    [call] = line.calls
    assert (call.kind, call.text, call.cards, call.with_images) == (
        "reply",
        "Two options.",
        CARDS,
        True,
    )


async def test_cards_alone_are_sent() -> None:
    line = FakeLine()
    sent = await AnswerSender(line).send(GROUP, TOKEN, Answer(None, CARDS))
    assert sent == Answer(None, CARDS)
    assert line.calls[0].text is None and line.calls[0].cards == CARDS


async def test_a_refused_message_is_tried_once_more_without_images() -> None:
    line = FakeLine(reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.SENT])
    sent = await AnswerSender(line).send(GROUP, TOKEN, BOTH)
    assert sent == BOTH
    assert [(c.kind, c.with_images) for c in line.calls] == [("reply", True), ("reply", False)]


async def test_cards_refused_twice_fall_back_to_a_push_of_the_text_only() -> None:
    line = FakeLine(reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.MESSAGE_REFUSED])
    sent = await AnswerSender(line).send(GROUP, TOKEN, BOTH)
    assert sent == Answer("Two options.", [])
    assert [(c.kind, c.cards) for c in line.calls] == [
        ("reply", CARDS),
        ("reply", CARDS),
        ("push", []),
    ]
    assert line.pushes == [(GROUP, "Two options.")]


async def test_cards_refused_twice_with_no_text_send_nothing_more() -> None:
    line = FakeLine(reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.MESSAGE_REFUSED])
    assert await AnswerSender(line).send(GROUP, TOKEN, Answer(None, CARDS)) is None
    assert line.pushes == []


async def test_a_refused_token_pushes_the_cards_too() -> None:
    line = FakeLine(reply_accepts=False)
    sent = await AnswerSender(line).send(GROUP, TOKEN, BOTH)
    assert sent == BOTH
    assert [(c.kind, c.cards, c.with_images) for c in line.calls] == [
        ("reply", CARDS, True),
        ("push", CARDS, True),
    ]


async def test_a_push_the_cards_make_fail_is_sent_again_as_text_only() -> None:
    line = FakeLine(reply_accepts=False, push_statuses=[400, None])
    sent = await AnswerSender(line).send(GROUP, TOKEN, BOTH)
    assert sent == Answer("Two options.", [])
    assert [c.cards for c in line.calls if c.kind == "push"] == [CARDS, []]


async def test_a_push_failure_that_is_not_about_the_cards_is_raised() -> None:
    line = FakeLine(reply_accepts=False, push_statuses=[429])
    with pytest.raises(LineApiError):
        await AnswerSender(line).send(GROUP, TOKEN, BOTH)
    assert len(line.calls) == 2


async def test_without_a_reply_token_it_pushes() -> None:
    line = FakeLine()
    sent = await AnswerSender(line).send(GROUP, None, BOTH)
    assert sent == BOTH and [c.kind for c in line.calls] == ["push"]


async def test_a_reply_that_fails_otherwise_is_not_retried_or_pushed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class Failing(FakeLine):
        async def reply(self, *args: object, **kwargs: object) -> ReplyResult:
            raise LineApiError("reply", 500)

    line = Failing()
    with caplog.at_level(logging.INFO):
        assert await AnswerSender(line).send(GROUP, TOKEN, BOTH) is None
    assert line.calls == []
    assert "status 500" in caplog.text
    assert "Two options." not in caplog.text and "example.com" not in caplog.text


async def test_the_text_and_the_cards_are_made_plain_before_they_are_sent() -> None:
    line = FakeLine()
    card = Card("**Gion Inn**", "- near the station", "https://example.com/1")
    sent = await AnswerSender(line).send(GROUP, TOKEN, Answer("# Hotels\n- **Gion Inn**", [card]))
    [call] = line.calls
    assert call.text == "Hotels\n・Gion Inn"
    assert (call.cards[0].title, call.cards[0].text) == ("Gion Inn", "・near the station")
    assert sent is not None and sent.text == "Hotels\n・Gion Inn"


async def test_the_reply_and_the_push_quote_the_message() -> None:
    line = FakeLine()
    await AnswerSender(line).send(GROUP, TOKEN, Answer("Hi."), quote_token="q1")
    line = FakeLine(reply_accepts=False)
    await AnswerSender(line).send(GROUP, TOKEN, Answer("Hi."), quote_token="q1")
    assert [(c.kind, c.quote_token) for c in line.calls] == [("reply", "q1"), ("push", "q1")]


async def test_a_push_the_quote_makes_fail_is_sent_again_without_it() -> None:
    line = FakeLine(reply_accepts=False, push_statuses=[400, None])
    sent = await AnswerSender(line).send(GROUP, None, BOTH, quote_token="q1")
    assert sent == BOTH
    assert [(c.cards, c.quote_token) for c in line.calls] == [(CARDS, "q1"), (CARDS, None)]


async def test_a_push_that_fails_even_without_the_quote_and_cards_is_raised() -> None:
    line = FakeLine(push_statuses=[400, 400])
    with pytest.raises(LineApiError):
        await AnswerSender(line).send(GROUP, None, Answer("Hi."), quote_token="q1")
    assert [c.quote_token for c in line.calls] == ["q1", None]


class RecordingNotifier:
    def __init__(self) -> None:
        self.failures = 0

    async def note_send_failed(self) -> None:
        self.failures += 1


async def test_a_reply_that_failed_is_reported_to_the_alert_notifier() -> None:
    class Failing(FakeLine):
        async def reply(self, *args: object, **kwargs: object) -> ReplyResult:
            raise LineApiError("reply", 500)

    notifier = RecordingNotifier()
    sender = AnswerSender(Failing(), notifier=notifier)  # type: ignore[arg-type]
    assert await sender.send(GROUP, TOKEN, BOTH) is None
    assert notifier.failures == 1


async def test_a_push_that_failed_is_reported_once_and_still_raised() -> None:
    notifier = RecordingNotifier()
    sender = AnswerSender(FakeLine(push_statuses=[500]), notifier=notifier)  # type: ignore[arg-type]
    with pytest.raises(LineApiError):
        await sender.send(GROUP, None, BOTH)
    assert notifier.failures == 1


async def test_a_card_or_quote_that_was_loosened_is_not_reported_as_a_failure() -> None:
    notifier = RecordingNotifier()
    line = FakeLine(push_statuses=[400, 400, None])
    sender = AnswerSender(line, notifier=notifier)  # type: ignore[arg-type]
    await sender.send(GROUP, None, BOTH, quote_token="q1")
    assert notifier.failures == 0


POLL = OutgoingExtra({"type": "flex"}, "[投票] p1 Where?")
QUICK = [QuickReplyItem("Kyoto", "Sora、Kyoto")]


async def test_extra_messages_and_quick_replies_go_out_with_the_reply() -> None:
    line = FakeLine()
    answer = Answer("Vote below.", extras=[POLL], quick_replies=QUICK)
    sent = await AnswerSender(line).send(GROUP, TOKEN, answer)
    assert sent == answer
    [call] = line.calls
    assert call.extras == [POLL] and call.quick_replies == QUICK


async def test_an_extra_message_alone_is_sent() -> None:
    line = FakeLine()
    sent = await AnswerSender(line).send(GROUP, TOKEN, Answer(None, extras=[POLL]))
    assert sent is not None and sent.extras == [POLL]


async def test_extras_refused_twice_fall_back_to_a_push_of_the_text_only() -> None:
    line = FakeLine(reply_results=[ReplyResult.MESSAGE_REFUSED, ReplyResult.MESSAGE_REFUSED])
    sent = await AnswerSender(line).send(
        GROUP, TOKEN, Answer("Vote below.", extras=[POLL], quick_replies=QUICK)
    )
    assert sent == Answer("Vote below.")
    assert [(c.kind, c.extras) for c in line.calls] == [
        ("reply", [POLL]),
        ("reply", [POLL]),
        ("push", []),
    ]


async def test_a_push_refused_with_extras_is_tried_again_with_the_text_only() -> None:
    line = FakeLine(reply_accepts=False, push_statuses=[400, None])
    sent = await AnswerSender(line).send(GROUP, TOKEN, Answer("Vote below.", extras=[POLL]))
    assert sent == Answer("Vote below.")
    assert [c.extras for c in line.calls if c.kind == "push"] == [[POLL], []]
