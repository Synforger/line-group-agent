"""What a client tool is: a name and definition the model sees, and the function that runs
when the model calls it.

A client tool runs inside this agent, reads and changes the group's own files, and may add
messages to the reply through the turn's output. A tool that has to wait (drawing an image)
is async, so the agent keeps handling other events meanwhile; the others run to the end
without waiting, on the event loop. Built by the feature folders
(polls, itinerary, bills, media) and collected by `ClientTools`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.records.group_log import GroupMessage


@dataclass(frozen=True)
class ToolTurn:
    """What a tool may use while it runs: the group, the mention that started the turn, and
    the output that the turn's tools add to."""

    group_id: str
    mention: GroupMessage
    output: TurnOutput


@dataclass(frozen=True)
class ToolOutcome:
    """The text sent back to the model as the tool's result; `is_error` marks a refused call."""

    content: str
    is_error: bool = False


@dataclass(frozen=True)
class ClientTool:
    """One tool: `definition` is the API's tool object, `run` takes the model's input and
    returns the outcome, or an awaitable of it for a tool that waits."""

    name: str
    definition: dict[str, Any]
    run: Callable[[object, ToolTurn], ToolOutcome | Awaitable[ToolOutcome]]
