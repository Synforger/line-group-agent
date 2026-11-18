"""Handle webhook events one at a time, after the webhook has already answered 200.

The webhook endpoint queues events here. For an allowed group, each text message is
recorded, and a message that mentions the bot is answered through the answerer.
Everything else is dropped; a join or an event from a group not on the list logs that
group's id (and nothing else) so the operator can add it.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any, Protocol

from line_group_agent.events.event_fields import (
    group_id_of,
    is_self_mentioned,
    is_text_message,
    local_time_of,
)
from line_group_agent.line_api.line_client import LineApiError, LineClient
from line_group_agent.records.group_log import GroupLog, GroupMessage

logger = logging.getLogger(__name__)

QUEUE_CAPACITY = 1000


class MentionAnswerer(Protocol):
    """What the dispatcher needs from the answerer."""

    async def answer(self, group_id: str, mention: GroupMessage) -> str | None: ...


class EventDispatcher:
    """A queue of webhook events and the one worker that handles them in order."""

    def __init__(
        self,
        allowed_group_ids: frozenset[str],
        line: LineClient,
        group_log: GroupLog,
        answerer: MentionAnswerer,
    ) -> None:
        self.allowed_group_ids = allowed_group_ids
        self.line = line
        self.group_log = group_log
        self.answerer = answerer
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
        if group_id not in self.allowed_group_ids:
            self._report_group(event, group_id)
            return
        if not is_text_message(event):
            return

        message = event["message"]
        source = event.get("source") or {}
        user_id = source.get("userId") if isinstance(source.get("userId"), str) else None
        record = GroupMessage(
            time=local_time_of(event),
            message_id=str(message.get("id", "")),
            user_id=user_id,
            display_name=await self._name_of(group_id, user_id),
            text=message["text"],
        )
        self.group_log.add(group_id, record)

        if not is_self_mentioned(event):
            return
        text = await self.answerer.answer(group_id, record)
        if text is None:
            logger.info("answer: no reply to send")
            return
        await self._send(group_id, event.get("replyToken"), text)

    async def _work(self) -> None:
        while True:
            event = await self._queue.get()
            try:
                await self.handle(event)
            except Exception as error:  # one bad event must not stop the worker
                logger.error("events: handling failed (%s)", type(error).__name__)
            finally:
                self._queue.task_done()

    def _report_group(self, event: dict[str, Any], group_id: str) -> None:
        if event.get("type") == "join":
            logger.warning("join: joined a group that is not allowed: group_id=%s", group_id)
        elif group_id not in self._reported_groups:
            logger.warning("events: dropped events of a group not allowed: group_id=%s", group_id)
        self._reported_groups.add(group_id)

    async def _name_of(self, group_id: str, user_id: str | None) -> str | None:
        if user_id is None:
            return None
        key = (group_id, user_id)
        if key not in self._names:
            self._names[key] = await self.line.get_member_name(group_id, user_id)
        return self._names[key]

    async def _send(self, group_id: str, reply_token: Any, text: str) -> None:
        # Push only when LINE refused the reply token; on any other failure the reply
        # may have been delivered, and a push would send the answer twice.
        if isinstance(reply_token, str) and reply_token:
            try:
                if await self.line.reply(reply_token, text):
                    return
            except LineApiError as error:
                logger.warning("reply: failed (status %d); not retrying", error.status)
                return
            logger.info("reply: the reply token was refused; sending by push instead")
        await self.line.push(group_id, text)
