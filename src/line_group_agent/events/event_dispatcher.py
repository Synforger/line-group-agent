"""Handle webhook events one at a time, after the webhook has already answered 200.

The webhook endpoint queues events here. For an allowed group, each text message is
recorded, and a message that mentions the bot is answered through the answerer, quoting
the message and with a fixed text instead when no answer could be made. The reply, once
sent, is recorded too (with a line naming any cards that went with it), so the next
mention sees what the bot said.

Around a mention: one person may call the bot only so many times an hour (then they are
told once, and not answered); when the answerer says the answer will take a while, a
"one moment" text goes out first through the reply token and the answer follows by push.
A message a member takes back (unsend) is deleted from the records. When the bot joins
an allowed group it introduces itself with a fixed text.

Everything else is dropped; a join or an event from a group not on the list logs that
group's id (and nothing else) so the operator can add it.

When a required member is configured, the bot leaves a group that is not on the list
as soon as it hears from it, unless that member is in the group (LINE is asked; a
group whose membership cannot be confirmed is left too). With
`allow_groups_with_required_member`, a group that member is in counts as allowed; the
membership is asked again after an hour, and the bot leaves once the member is gone.

LINE may send an event again after a failed delivery (webhook redelivery). A message
whose id is already in the group's record is skipped, so it is recorded and answered
once. A redelivered mention older than the answer window is recorded but not answered.

The group watcher is told of each recorded message and after each answer, so it can
register the group, roll a full conversation over and keep the tab list current.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from line_group_agent.agent.answerer import Answer, SlowNotice
from line_group_agent.agent.message_deleter import MessageDeleter
from line_group_agent.alerts.alert_notifier import AlertNotifier
from line_group_agent.cards.card_record import format_card_record
from line_group_agent.events.answer_sender import AnswerSender
from line_group_agent.events.event_fields import (
    age_seconds_of,
    group_id_of,
    is_redelivery,
    is_self_mentioned,
    is_text_message,
    local_time_of,
    quote_token_of,
    unsent_message_id_of,
)
from line_group_agent.events.mention_limiter import MentionLimiter, MentionVerdict
from line_group_agent.events.wait_notice import WaitNotice
from line_group_agent.line_api.line_client import LineApiError, LineClient
from line_group_agent.records.group_log import GroupLog, GroupMessage

logger = logging.getLogger(__name__)

QUEUE_CAPACITY = 1000
DEFAULT_REDELIVERED_ANSWER_WINDOW_SECONDS = 600
MEMBERSHIP_RECHECK_SECONDS = 3600


class GroupObserver(Protocol):
    """What the dispatcher tells the group watcher."""

    async def note_message(self, group_id: str, message: GroupMessage) -> None: ...

    async def after_answer(self, group_id: str) -> None: ...

    async def after_deletion(self, group_id: str) -> None: ...


class MentionAnswerer(Protocol):
    """What the dispatcher needs from the answerer."""

    async def answer(
        self, group_id: str, mention: GroupMessage, *, on_slow: SlowNotice | None = None
    ) -> Answer: ...


@dataclass(frozen=True)
class NoticeTexts:
    """The fixed texts the dispatcher sends itself. An empty one is not sent."""

    error: str = ""
    rate_limit: str = ""
    intro: str = ""
    help: str = ""
    help_keywords: tuple[str, ...] = ()


class EventDispatcher:
    """A queue of webhook events and the one worker that handles them in order."""

    def __init__(
        self,
        allowed_group_ids: frozenset[str],
        line: LineClient,
        group_log: GroupLog,
        answerer: MentionAnswerer,
        *,
        redelivered_answer_window_seconds: int = DEFAULT_REDELIVERED_ANSWER_WINDOW_SECONDS,
        required_member_user_id: str | None = None,
        allow_groups_with_required_member: bool = False,
        observer: GroupObserver | None = None,
        texts: NoticeTexts | None = None,
        limiter: MentionLimiter | None = None,
        wait_notice: WaitNotice | None = None,
        deleter: MessageDeleter | None = None,
        notifier: AlertNotifier | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.allowed_group_ids = allowed_group_ids
        self.line = line
        self.group_log = group_log
        self.answerer = answerer
        self._sender = AnswerSender(line, notifier=notifier)
        self.texts = texts or NoticeTexts()
        self.limiter = limiter
        self.wait_notice = wait_notice
        self.deleter = deleter
        self.redelivered_answer_window_seconds = redelivered_answer_window_seconds
        self.required_member_user_id = required_member_user_id
        self.allow_groups_with_required_member = allow_groups_with_required_member
        self.observer = observer
        self._clock = clock
        self._membership: dict[str, tuple[bool | None, float]] = {}
        self._left_groups: set[str] = set()
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(QUEUE_CAPACITY)
        self._worker: asyncio.Task[None] | None = None
        self._names: dict[tuple[str, str], str | None] = {}
        self._reported_groups: set[str] = set()

    def start(self) -> None:
        """Start the worker on the running event loop."""
        if self._worker is None:
            self._worker = asyncio.create_task(self._work())

    async def stop(self) -> None:
        """Stop the worker; events still queued are dropped."""
        if self._worker is not None:
            self._worker.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._worker
            self._worker = None

    def add_events(self, events: list[Any]) -> None:
        """Queue events for the worker; returns at once."""
        for event in events:
            if not isinstance(event, dict):
                continue
            try:
                self._queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("events: queue full; an event was dropped")

    async def wait_idle(self) -> None:
        """Wait until every queued event has been handled."""
        await self._queue.join()

    async def handle(self, event: dict[str, Any]) -> None:
        """Handle one event (the worker calls this; tests may call it directly)."""
        group_id = group_id_of(event)
        if group_id is None:
            return
        if group_id not in self.allowed_group_ids and not await self._admit(event, group_id):
            return
        if event.get("type") == "join":
            await self._introduce(group_id, event)
            return
        if (unsent_id := unsent_message_id_of(event)) is not None:
            await self._forget(group_id, unsent_id)
            return
        if not is_text_message(event):
            return

        message = event["message"]
        message_id = str(message.get("id", ""))
        if message_id and self.group_log.has_message(group_id, message_id):
            logger.info("events: a message already handled arrived again; skipped")
            return
        source = event.get("source") or {}
        user_id = source.get("userId") if isinstance(source.get("userId"), str) else None
        record = GroupMessage(
            time=local_time_of(event),
            message_id=message_id,
            user_id=user_id,
            display_name=await self._name_of(group_id, user_id),
            text=message["text"],
        )
        self.group_log.add(group_id, record)
        if self.observer is not None:
            await self.observer.note_message(group_id, record)

        if not is_self_mentioned(event):
            return
        if is_redelivery(event) and self._is_too_old(event):
            logger.info("answer: a redelivered mention is past the answer window; not answered")
            return
        verdict = MentionVerdict.ANSWER if self.limiter is None else self.limiter.check(user_id)
        if verdict is not MentionVerdict.ANSWER:
            if verdict is MentionVerdict.REFUSE_AND_TELL:
                await self._tell_rate_limit(group_id, event)
            return
        if self._asks_for_help(event):
            await self._send_help(group_id, event)
            return
        await self._answer_mention(group_id, event, record)

    async def _answer_mention(
        self, group_id: str, event: dict[str, Any], record: GroupMessage
    ) -> None:
        is_token_used = False

        async def announce_wait() -> None:
            nonlocal is_token_used
            if self.wait_notice is not None and await self.wait_notice.send(
                event.get("replyToken")
            ):
                is_token_used = True

        try:
            answer = await self.answerer.answer(group_id, record, on_slow=announce_wait)
        except Exception as error:  # a failed answer is told to the group, not dropped
            logger.error("answer: failed (%s)", type(error).__name__)
            answer = Answer(self.texts.error or None)
        try:
            token = None if is_token_used else event.get("replyToken")
            await self._deliver(group_id, token, quote_token_of(event), answer)
        finally:
            if self.observer is not None:
                await self.observer.after_answer(group_id)

    async def _deliver(
        self, group_id: str, reply_token: Any, quote_token: str | None, answer: Answer
    ) -> None:
        if not answer.text and not answer.cards:
            logger.info("answer: no reply to send")
            return
        sent = await self._sender.send(group_id, reply_token, answer, quote_token=quote_token)
        if sent is not None and answer.record:
            self.group_log.add(group_id, _bot_reply(sent))

    async def _tell_rate_limit(self, group_id: str, event: dict[str, Any]) -> None:
        logger.info("answer: a member passed the hourly limit; not answered")
        if self.texts.rate_limit:
            await self._sender.send(
                group_id,
                event.get("replyToken"),
                Answer(self.texts.rate_limit),
                quote_token=quote_token_of(event),
            )

    def _asks_for_help(self, event: dict[str, Any]) -> bool:
        """Whether the mention, with the mention text removed, is only a help keyword."""
        if not self.texts.help or not self.texts.help_keywords:
            return False
        rest = _without_mentions(event).strip().strip("?？!！。、 ").casefold()
        return any(rest == keyword.casefold() for keyword in self.texts.help_keywords)

    async def _send_help(self, group_id: str, event: dict[str, Any]) -> None:
        # The list is sent as written, without calling the model (no cost). It is not
        # recorded as a turn, so the next mention still sees the messages around it.
        logger.info("answer: sent the capability list")
        await self._sender.send(
            group_id,
            event.get("replyToken"),
            Answer(self.texts.help, record=False),
            quote_token=quote_token_of(event),
        )

    async def _introduce(self, group_id: str, event: dict[str, Any]) -> None:
        if not self.texts.intro:
            return
        sent = await self._sender.send(group_id, event.get("replyToken"), Answer(self.texts.intro))
        if sent is None:
            return
        record = _bot_reply(sent)
        self.group_log.add(group_id, record)
        if self.observer is not None:
            await self.observer.note_message(group_id, record)

    async def _forget(self, group_id: str, message_id: str) -> None:
        if self.deleter is None:
            return
        if await self.deleter.delete_unsent(group_id, message_id) and self.observer is not None:
            await self.observer.after_deletion(group_id)

    def _is_too_old(self, event: dict[str, Any]) -> bool:
        age = age_seconds_of(event, datetime.now().astimezone())
        return age is not None and age > self.redelivered_answer_window_seconds

    async def _work(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self.handle(event)
            except Exception as error:  # one bad event must not stop the worker
                logger.error("events: handling failed (%s)", type(error).__name__)
            finally:
                self._queue.task_done()

    async def _admit(self, event: dict[str, Any], group_id: str) -> bool:
        """Decide an event from a group not on the configured list: True to handle it
        as an allowed group's event, False to drop it (leaving the group if needed)."""
        if group_id in self._left_groups:
            return False
        if self.required_member_user_id is not None:
            if await self._member_present(group_id) is not True:
                self._left_groups.add(group_id)
                await self._leave(group_id)
                return False
            if self.allow_groups_with_required_member:
                if group_id not in self._reported_groups:
                    logger.warning(
                        "events: allowed a group the member is in: group_id=%s", group_id
                    )
                    self._reported_groups.add(group_id)
                return True
        if group_id not in self._reported_groups:
            self._reported_groups.add(group_id)
            if event.get("type") == "join":
                logger.warning("join: joined a group that is not allowed: group_id=%s", group_id)
            else:
                logger.warning(
                    "events: dropped events of a group not allowed: group_id=%s", group_id
                )
        return False

    async def _member_present(self, group_id: str) -> bool | None:
        assert self.required_member_user_id is not None
        now = self._clock()
        cached = self._membership.get(group_id)
        if (
            cached is not None
            and cached[0] is True
            and now - cached[1] < MEMBERSHIP_RECHECK_SECONDS
        ):
            return True
        present = await self.line.is_member(group_id, self.required_member_user_id)
        self._membership[group_id] = (present, now)
        return present

    async def _leave(self, group_id: str) -> None:
        try:
            await self.line.leave_group(group_id)
        except LineApiError as error:
            logger.warning(
                "leave: could not leave a group without the required member "
                "(status %d): group_id=%s",
                error.status,
                group_id,
            )
            return
        logger.warning("leave: left a group without the required member: group_id=%s", group_id)

    async def _name_of(self, group_id: str, user_id: str | None) -> str | None:
        if user_id is None:
            return None
        key = (group_id, user_id)
        if key not in self._names:
            self._names[key] = await self.line.get_member_name(group_id, user_id)
        return self._names[key]


def _bot_reply(sent: Answer) -> GroupMessage:
    parts = [sent.text] if sent.text else []
    if sent.cards:
        parts.append(format_card_record(sent.cards))
    return GroupMessage(
        time=datetime.now().astimezone().isoformat(timespec="seconds"),
        message_id=f"bot-{uuid.uuid4()}",
        user_id=None,
        display_name=None,
        text="\n".join(parts),
        from_bot=True,
    )


def _without_mentions(event: dict[str, Any]) -> str:
    """Return the message text with every mentioned span (by index and length) removed."""
    message = event.get("message") or {}
    text = message.get("text") or ""
    mentionees = (message.get("mention") or {}).get("mentionees") or []
    spans = sorted(
        (m["index"], m["index"] + m["length"])
        for m in mentionees
        if isinstance(m, dict)
        and isinstance(m.get("index"), int)
        and isinstance(m.get("length"), int)
    )
    kept: list[str] = []
    position = 0
    for start, end in spans:
        kept.append(text[position:start])
        position = max(position, end)
    kept.append(text[position:])
    return "".join(kept)
