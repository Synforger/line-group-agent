"""Play one scenario against a running bot: for each step send a signed webhook event the way
LINE does, wait until the bot has handled it, and write down what the bot sent back.

The bot is told apart as done when its event dispatcher has no event left, so a reply that
comes by push after a "one moment" is waited for, and a bot that stays silent is not waited
on for a timeout. Called by the simulation.
"""

from __future__ import annotations

import asyncio
import json
import mimetypes
import secrets
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from line_group_agent.simulator.fake_line_server import FakeLineServer, RecordedCall
from line_group_agent.simulator.id_token import make_id_token
from line_group_agent.simulator.message_actions import list_actions
from line_group_agent.simulator.scenario import (
    ActionRef,
    ImageStep,
    LocationStep,
    OpenLiffStep,
    PressStep,
    Scenario,
    Step,
    TextStep,
    WaitStep,
)
from line_group_agent.simulator.screen_capture import ScreenCapture
from line_group_agent.simulator.transcript import (
    OutputRecord,
    ScenarioTranscript,
    SpendFigure,
    StepRecord,
)
from line_group_agent.simulator.webhook_events import (
    BotMention,
    EventIds,
    image_event,
    location_event,
    postback_event,
    sign_body,
    text_event,
    webhook_body,
)

WEBHOOK_PATH = "/line/webhook"
LIFF_HOST = "liff.line.me"
LIFF_PAGE_PATH = "/liff/"
FIRST_MESSAGE_ID = 100000000000
HTTP_OK = 200
SPEND_FILE_NAME = "spend.json"
DEFAULT_IMAGE_TYPE = "application/octet-stream"


class StepProblem(Exception):
    """A step could not be played; the message goes into the step's record."""


class EventSink(Protocol):
    """What the runner needs from the bot's event dispatcher."""

    async def wait_idle(self) -> None: ...


class ScenarioRunner:
    """Plays the steps of one scenario in order and returns the transcript."""

    def __init__(
        self,
        scenario: Scenario,
        *,
        line: FakeLineServer,
        bot_url: str,
        channel_secret: str,
        event_sink: EventSink,
        state_dir: Path,
        currency: str,
        currency_per_usd: float,
        screens: ScreenCapture | None,
        screens_dir: Path,
        step_timeout_seconds: float,
        max_usd: float | None = None,
    ) -> None:
        self.scenario = scenario
        self._line = line
        self._bot_url = bot_url
        self._channel_secret = channel_secret
        self._sink = event_sink
        self._state_dir = state_dir
        self._currency = currency
        self._currency_per_usd = currency_per_usd
        self._screens = screens
        self._screens_dir = screens_dir
        self._step_timeout_seconds = step_timeout_seconds
        self._max_usd = max_usd
        self._counter = 0
        self._http = httpx.AsyncClient(timeout=step_timeout_seconds, trust_env=False)

    async def run(self) -> ScenarioTranscript:
        """Play every step (or until the spend guard stops it) and return what happened."""
        transcript = ScenarioTranscript(
            slug=self.scenario.slug,
            name=self.scenario.name,
            group={
                "id": self.scenario.group.id,
                "name": self.scenario.group.name,
                "members": [asdict(member) for member in self.scenario.group.members],
            },
            bot_name=self.scenario.bot_name,
            started_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        started = time.monotonic()
        spent_before = self._spent()
        try:
            for index, step in enumerate(self.scenario.steps):
                record = await self._play(index, step)
                transcript.steps.append(record)
                if self._is_over_budget(spent_before):
                    transcript.stopped_reason = f"stopped after step {index}: spend guard"
                    break
        finally:
            await self._http.aclose()
        transcript.total_seconds = round(time.monotonic() - started, 3)
        transcript.total_spend = self._figure(self._spent() - spent_before)
        transcript.error_count = sum(1 for step in transcript.steps if step.error)
        transcript.api_calls = [_summary_of(call) for call in self._line.calls]
        return transcript

    async def _play(self, index: int, step: Step) -> StepRecord:
        sent_before = len(self._line.sent_calls())
        began = time.monotonic()
        began_elapsed = self._line.elapsed_seconds()
        spent_before = self._spent()
        record = StepRecord(
            index=index,
            kind=_kind_of(step),
            sender=getattr(step, "sender", None),
            sender_name=None,
            input=_input_of(step),
            shown=None,
            event=None,
            outputs=[],
            seconds=0.0,
            first_output_seconds=None,
            spend=self._figure(0.0),
        )
        if record.sender is not None:
            record.sender_name = self.scenario.member_named(record.sender).name
        try:
            await self._act(step, record)
        except StepProblem as problem:
            record.error = str(problem)
        record.seconds = round(time.monotonic() - began, 3)
        for position, call in enumerate(self._line.sent_calls()[sent_before:], start=sent_before):
            record.outputs.append(
                OutputRecord(
                    output_index=position,
                    kind=call.kind,
                    at_seconds=round(call.at_seconds - began_elapsed, 3),
                    target=call.target,
                    messages=call.messages,
                )
            )
        if record.outputs:
            record.first_output_seconds = record.outputs[0].at_seconds
        record.spend = self._figure(self._spent() - spent_before)
        return record

    async def _act(self, step: Step, record: StepRecord) -> None:
        group_id = self.scenario.group.id
        if isinstance(step, WaitStep):
            record.shown = {"type": "wait", "seconds": step.seconds}
            await asyncio.sleep(step.seconds)
        elif isinstance(step, TextStep):
            mention = (
                BotMention(self.scenario.bot_user_id, self.scenario.bot_name)
                if step.mention
                else None
            )
            event = text_event(group_id, step.sender, step.text, self._new_ids(), mention)
            record.shown = {"type": "text", "text": event["message"]["text"]}
            await self._send(event, record)
        elif isinstance(step, ImageStep):
            ids = self._new_ids()
            content_type = mimetypes.guess_type(step.image_file.name)[0] or DEFAULT_IMAGE_TYPE
            self._line.add_content(ids.message_id, step.image_file.read_bytes(), content_type)
            record.shown = {"type": "image", "file": str(step.image_file)}
            await self._send(image_event(group_id, step.sender, ids), record)
        elif isinstance(step, LocationStep):
            event = location_event(
                group_id,
                step.sender,
                self._new_ids(),
                title=step.title,
                address=step.address,
                latitude=step.latitude,
                longitude=step.longitude,
            )
            record.shown = {key: event["message"][key] for key in _LOCATION_KEYS}
            record.shown["type"] = "location"
            await self._send(event, record)
        elif isinstance(step, PressStep):
            await self._press(step, record)
        else:
            await self._open_liff(step, record)

    async def _press(self, step: PressStep, record: StepRecord) -> None:
        action = self._action_of(step.target)
        group_id = self.scenario.group.id
        kind = action.get("type")
        if kind == "postback" and isinstance(action.get("data"), str):
            record.shown = {
                "type": "press",
                "label": action.get("label", ""),
                "display_text": action.get("displayText"),
            }
            event = postback_event(group_id, step.sender, action["data"], self._new_ids())
        elif kind == "message" and isinstance(action.get("text"), str):
            record.shown = {"type": "text", "text": action["text"]}
            event = text_event(group_id, step.sender, action["text"], self._new_ids())
        elif kind == "uri":
            record.shown = {"type": "press", "label": action.get("label", ""), "display_text": None}
            record.note = "a link button: nothing is sent to the bot (use open_liff for LIFF)"
            return
        else:
            raise StepProblem(f"cannot press an action of type {kind!r}")
        await self._send(event, record)

    async def _open_liff(self, step: OpenLiffStep, record: StepRecord) -> None:
        action = self._action_of(step.target)
        address = urlsplit(str(action.get("uri", "")))
        if action.get("type") != "uri" or address.hostname != LIFF_HOST:
            raise StepProblem("the action is not a link to a LIFF page")
        page_url = f"{self._bot_url}{LIFF_PAGE_PATH}?{address.query}"
        record.shown = {"type": "open_liff", "url": str(action["uri"])}
        if self._screens is None:
            record.note = "screens are off: the page was not opened"
            return
        member = self.scenario.member_named(step.sender)
        token = make_id_token(member.user_id, member.name)
        path = self._screens_dir / f"step-{record.index:02d}-liff.png"
        record.note = await self._screens.capture_liff(page_url, token, path)
        record.screen = f"screens/{path.name}"

    def _action_of(self, target: ActionRef) -> dict[str, Any]:
        sent = self._line.sent_calls()
        if target.reply_index >= len(sent):
            raise StepProblem(f"the bot has sent only {len(sent)} replies so far")
        actions = list_actions(sent[target.reply_index].messages)
        if target.action_index >= len(actions):
            raise StepProblem(f"reply {target.reply_index} holds only {len(actions)} actions")
        return actions[target.action_index]

    async def _send(self, event: dict[str, Any], record: StepRecord) -> None:
        """Post the event to the bot signed like LINE's, then wait until the bot is done."""
        record.event = event
        self._line.issue_reply_token(event["replyToken"])
        body = webhook_body([event], self.scenario.bot_user_id)
        headers = {
            "x-line-signature": sign_body(body, self._channel_secret),
            "content-type": "application/json",
        }
        try:
            response = await self._http.post(
                f"{self._bot_url}{WEBHOOK_PATH}", content=body, headers=headers
            )
        except httpx.HTTPError as error:
            raise StepProblem(
                f"the bot did not take the webhook ({type(error).__name__})"
            ) from error
        if response.status_code != HTTP_OK:
            raise StepProblem(f"the bot answered the webhook with {response.status_code}")
        try:
            await asyncio.wait_for(self._sink.wait_idle(), self._step_timeout_seconds)
        except TimeoutError as error:
            raise StepProblem(
                f"the bot was not done within {self._step_timeout_seconds:g} seconds"
            ) from error

    def _new_ids(self) -> EventIds:
        self._counter += 1
        return EventIds(
            reply_token=secrets.token_hex(16),
            webhook_event_id=secrets.token_hex(13).upper(),
            message_id=str(FIRST_MESSAGE_ID + self._counter),
            quote_token=secrets.token_urlsafe(24),
            timestamp_ms=int(time.time() * 1000),
        )

    def _spent(self) -> float:
        """Return what the bot's overall ledger says is spent, in the configured currency."""
        try:
            saved = json.loads((self._state_dir / SPEND_FILE_NAME).read_text(encoding="utf-8"))
            return float(saved["spent"])
        except (OSError, ValueError, KeyError, TypeError):
            return 0.0

    def _figure(self, amount: float) -> SpendFigure:
        return SpendFigure(
            amount=round(amount, 4),
            usd=round(amount / self._currency_per_usd, 5),
            currency=self._currency,
        )

    def _is_over_budget(self, spent_before: float) -> bool:
        if self._max_usd is None:
            return False
        return (self._spent() - spent_before) / self._currency_per_usd > self._max_usd


_LOCATION_KEYS = ("title", "address", "latitude", "longitude")


def _kind_of(step: Step) -> str:
    return {
        TextStep: "text",
        ImageStep: "image",
        LocationStep: "location",
        PressStep: "press",
        OpenLiffStep: "open_liff",
        WaitStep: "wait",
    }[type(step)]


def _input_of(step: Step) -> dict[str, Any]:
    values = asdict(step)
    for key, value in values.items():
        if isinstance(value, Path):
            values[key] = str(value)
    if "sender" in values:
        return {"from": values.pop("sender"), **values}
    return values


def _summary_of(call: RecordedCall) -> dict[str, Any]:
    return {
        "at_seconds": call.at_seconds,
        "method": call.method,
        "path": call.path,
        "status": call.status,
        "kind": call.kind,
    }
