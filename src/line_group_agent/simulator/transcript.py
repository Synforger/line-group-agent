"""What one scripted chat produced: for each step what went in, what the bot sent back, how
long it took and what it cost.

Plain values; written as `transcript.json` and read by the pages. Built by the runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OutputRecord:
    """One reply or push the bot made. `output_index` counts them from 0 over the whole
    scenario, which is what a `press` or `open_liff` step names; `at_seconds` is the time
    since the step's input was sent."""

    output_index: int
    kind: str
    at_seconds: float
    target: str
    messages: list[dict[str, Any]]


@dataclass
class SpendFigure:
    """Money spent: `amount` in the configured currency and the same in US dollars."""

    amount: float
    usd: float
    currency: str


@dataclass
class StepRecord:
    """One step: its `input` as the scenario gave it, what `shown` in the chat for the
    member, the webhook `event` sent (None when none was), the bot's `outputs`, the seconds
    until the bot was done and the spend of the step. A LIFF page the member used leaves its
    `screen`, the messages it had sent as the member (`liff_sent`) and what it passed to the
    share target picker (`liff_shared`)."""

    index: int
    kind: str
    sender: str | None
    sender_name: str | None
    input: dict[str, Any]
    shown: dict[str, Any] | None
    event: dict[str, Any] | None
    outputs: list[OutputRecord]
    seconds: float
    first_output_seconds: float | None
    spend: SpendFigure
    note: str | None = None
    error: str | None = None
    screen: str | None = None
    liff_sent: list[dict[str, Any]] = field(default_factory=list)
    liff_shared: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ScenarioTranscript:
    """A whole scripted chat. `stopped_reason` says why it ended before its last step."""

    slug: str
    name: str
    group: dict[str, Any]
    bot_name: str
    started_at: str
    steps: list[StepRecord] = field(default_factory=list)
    api_calls: list[dict[str, Any]] = field(default_factory=list)
    total_seconds: float = 0.0
    total_spend: SpendFigure | None = None
    error_count: int = 0
    stopped_reason: str | None = None
