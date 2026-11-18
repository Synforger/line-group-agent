import logging

import pytest

from line_group_agent.agent.answerer import Answer
from line_group_agent.cards.card import Card
from line_group_agent.events.answer_sender import AnswerSender
from line_group_agent.line_api.line_client import LineApiError, ReplyResult
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
