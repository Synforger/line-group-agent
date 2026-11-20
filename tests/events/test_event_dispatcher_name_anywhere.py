"""A name that stands anywhere in a message (`call_name_anywhere`): the model reads the
message and may stay silent; a mention or a name at either end is answered as before."""

import json
from pathlib import Path
from typing import Any

import pytest

from line_group_agent.events.event_dispatcher import EventDispatcher, NoticeTexts
from line_group_agent.events.mention_limiter import MentionLimiter
from line_group_agent.records.group_log import GroupLog
from tests.events.test_event_dispatcher import ALLOWED, ScriptedAnswerer, text_event
from tests.fakes import FakeLine, answer, text_answer
from tests.world import GROUP, build_world

pytestmark = pytest.mark.anyio
MIDDLE = "昨日ソラに聞いたら便利だった"


def build(
    tmp_path: Path, *, is_anywhere: bool = True, **options: Any
) -> tuple[EventDispatcher, FakeLine, ScriptedAnswerer]:
    line = FakeLine(names={"U1": "Aki"})
    answerer = ScriptedAnswerer()
    dispatcher = EventDispatcher(
        frozenset({ALLOWED}),
        line,
        GroupLog(tmp_path),
        answerer,
        call_names=("ソラ", "Sora"),
        call_name_anywhere=is_anywhere,
        **options,
    )
    return dispatcher, line, answerer


async def test_a_name_in_the_middle_is_read_and_marked_as_a_name_only(tmp_path: Path) -> None:
    dispatcher, line, answerer = build(tmp_path)
    await dispatcher.handle(text_event(text=MIDDLE))
    assert [mention.text for _, mention in answerer.calls] == [MIDDLE]
    assert answerer.name_only_flags == [True]
    assert line.replies == [("reply-token-1", "Sure.")]


async def test_without_the_setting_a_name_in_the_middle_is_only_recorded(tmp_path: Path) -> None:
    dispatcher, line, answerer = build(tmp_path, is_anywhere=False)
    await dispatcher.handle(text_event(text=MIDDLE))
    assert answerer.calls == [] and line.calls == []


async def test_a_message_without_any_name_is_not_read(tmp_path: Path) -> None:
    dispatcher, _, answerer = build(tmp_path)
    await dispatcher.handle(text_event(text="明日どこ行く?"))
    await dispatcher.handle(text_event(text="Soraya Live", message_id="m2"))
    assert answerer.calls == []


async def test_a_mention_and_a_name_at_either_end_are_not_marked(tmp_path: Path) -> None:
    dispatcher, _, answerer = build(tmp_path)
    await dispatcher.handle(text_event(text="@bot 明日どこ?", mentions_bot=True))
    await dispatcher.handle(text_event(text="ソラ、明日どこ?", message_id="m2"))
    await dispatcher.handle(text_event(text="明日どこ?ソラ", message_id="m3"))
    assert answerer.name_only_flags == [False, False, False]


async def test_a_name_only_message_over_the_limit_is_skipped_without_a_notice(
    tmp_path: Path,
) -> None:
    dispatcher, line, answerer = build(
        tmp_path,
        limiter=MentionLimiter(1),
        texts=NoticeTexts(rate_limit="Too many asks."),
    )
    await dispatcher.handle(text_event(text=MIDDLE, message_id="m1"))
    await dispatcher.handle(text_event(text="またソラの話だけど", message_id="m2"))
    assert len(answerer.calls) == 1
    assert [text for _, text in line.replies] == ["Sure."]


async def test_a_mention_over_the_limit_is_still_told(tmp_path: Path) -> None:
    dispatcher, line, answerer = build(
        tmp_path,
        limiter=MentionLimiter(1),
        texts=NoticeTexts(rate_limit="Too many asks."),
    )
    await dispatcher.handle(text_event(text=MIDDLE, message_id="m1"))
    await dispatcher.handle(text_event(text="@bot hi", message_id="m2", mentions_bot=True))
    assert len(answerer.calls) == 1
    assert [text for _, text in line.replies] == ["Sure.", "Too many asks."]


async def test_a_name_only_message_does_not_use_the_keyword_shortcuts(tmp_path: Path) -> None:
    dispatcher, line, answerer = build(
        tmp_path, texts=NoticeTexts(help="The list.", help_keywords=("help",))
    )
    await dispatcher.handle(text_event(text="ソラはhelpって言ってた"))
    assert len(answerer.calls) == 1 and line.replies == [("reply-token-1", "Sure.")]


async def test_a_silent_turn_sends_nothing_records_no_reply_and_moves_the_turn_on(
    tmp_path: Path,
) -> None:
    stay_silent = answer(
        [{"type": "tool_use", "id": "toolu_1", "name": "stay_silent", "input": {}}],
        message_id="msg_1",
        stop_reason="tool_use",
    )
    world = build_world(
        tmp_path, [stay_silent, text_answer("<reply>Try Gion.</reply>")], call_name_anywhere=True
    )
    line = FakeLine(names={"U1": "Aki"})
    dispatcher = EventDispatcher(
        frozenset({GROUP}),
        line,
        world.group_log,
        world.answerer,
        call_names=("ソラ",),
        call_name_anywhere=True,
    )
    await dispatcher.handle(text_event(group_id=GROUP, text=MIDDLE, message_id="m1"))
    assert line.calls == []
    assert [m.from_bot for m in world.group_log.list_recent(GROUP, 10)] == [False]

    await dispatcher.handle(
        text_event(group_id=GROUP, text="@bot 宿は?", message_id="m2", mentions_bot=True)
    )
    assert line.replies == [("reply-token-1", "Try Gion.")]
    # The silent message was read in the first turn and is not handed over again.
    second = world.client.messages.requests[1]["messages"]
    assert [m["role"] for m in second] == ["user", "assistant", "user", "user"]
    assert MIDDLE not in json.dumps(second[3], ensure_ascii=False)
    assert MIDDLE in json.dumps(second[0], ensure_ascii=False)


async def test_a_name_that_runs_on_is_read_like_a_name_in_the_text(tmp_path: Path) -> None:
    dispatcher, _, answerer = build(tmp_path, call_name_start_runs_on=True)
    await dispatcher.handle(text_event(text="ソラって便利だよね"))
    await dispatcher.handle(text_event(text="ソラ、明日どこ?", message_id="m2"))
    assert answerer.name_only_flags == [True, False]


async def test_without_the_setting_a_name_that_runs_on_is_a_call(tmp_path: Path) -> None:
    dispatcher, _, answerer = build(tmp_path, is_anywhere=False, call_name_start_runs_on=True)
    await dispatcher.handle(text_event(text="ソラ候補出して"))
    assert answerer.name_only_flags == [False]
