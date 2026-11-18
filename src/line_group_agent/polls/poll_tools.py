"""The tools the model uses to run polls: make one, read the count, close it.

A poll goes out as a card after the reply text; votes are counted by the agent without the
model (see the postback handler). Called by the service builder, which adds the tools to
the client tools.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from line_group_agent._common.one_line import one_line
from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.polls.poll import KIND_CHOICE, Poll
from line_group_agent.polls.poll_book import PollBook
from line_group_agent.polls.poll_message import (
    OPTION_MAX_CHARS,
    QUESTION_MAX_CHARS,
    build_poll_message,
)
from line_group_agent.polls.poll_text import format_poll_results, poll_record_line

CREATE_POLL_TOOL_NAME = "create_poll"
POLL_RESULTS_TOOL_NAME = "poll_results"
CLOSE_POLL_TOOL_NAME = "close_poll"
MIN_OPTION_COUNT = 2
MAX_OPTION_COUNT = 10
NO_ROOM_RESULT = "This reply already holds as many extra messages as LINE allows. Nothing was made."
NO_POLL_RESULT = "There is no such poll in this group."
BAD_OPTIONS_RESULT = (
    f"Give a question and {MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} different, non-empty options."
)


def poll_tools(book: PollBook) -> list[ClientTool]:
    """Return the poll tools, working on `book`."""

    def create(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        question = one_line(fields.get("question"), QUESTION_MAX_CHARS)
        labels = clean_labels(fields.get("options"))
        if not question or labels is None:
            return ToolOutcome(BAD_OPTIONS_RESULT, is_error=True)
        if not turn.output.has_room():
            return ToolOutcome(NO_ROOM_RESULT, is_error=True)
        poll = book.create(
            turn.group_id,
            question,
            labels,
            kind=KIND_CHOICE,
            multiple=fields.get("multiple") is True,
        )
        turn.output.add(_extra_of(poll))
        return ToolOutcome(
            f"Poll {poll.id} is sent as a card after your reply. Members vote with its buttons; "
            "votes are counted without you, so call poll_results when someone asks for the count."
        )

    def results(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        poll = book.get(turn.group_id, _poll_id_of(tool_input))
        if poll is None:
            return ToolOutcome(NO_POLL_RESULT, is_error=True)
        return ToolOutcome(format_poll_results(poll))

    def close(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        poll = book.close(turn.group_id, _poll_id_of(tool_input))
        if poll is None:
            return ToolOutcome("There is no open poll to close.", is_error=True)
        return ToolOutcome(f"Poll {poll.id} is closed. Final count:\n{format_poll_results(poll)}")

    return [
        ClientTool(CREATE_POLL_TOOL_NAME, _create_definition(), create),
        ClientTool(POLL_RESULTS_TOOL_NAME, _results_definition(), results),
        ClientTool(CLOSE_POLL_TOOL_NAME, _close_definition(), close),
    ]


def clean_labels(raw: object) -> list[str] | None:
    """Return the options (or dates) as short one-line labels, or None unless there are 2 to
    10 different non-empty ones."""
    if not isinstance(raw, Sequence) or isinstance(raw, str):
        return None
    labels = [one_line(item, OPTION_MAX_CHARS) for item in raw]
    if not MIN_OPTION_COUNT <= len(labels) <= MAX_OPTION_COUNT:
        return None
    if not all(labels) or len(set(labels)) != len(labels):
        return None
    return labels


def _extra_of(poll: Poll) -> OutgoingExtra:
    return OutgoingExtra(build_poll_message(poll), poll_record_line(poll))


def _poll_id_of(tool_input: object) -> str | None:
    poll_id = tool_input.get("poll_id") if isinstance(tool_input, dict) else None
    return poll_id if isinstance(poll_id, str) and poll_id.strip() else None


def _create_definition() -> dict[str, Any]:
    return {
        "name": CREATE_POLL_TOOL_NAME,
        "description": (
            "Start a vote in the group. It is sent as a card with one button per option, "
            "after your reply; members vote by pressing a button, one vote each (or several "
            "with multiple). Use it when a member asks for a vote. Write a short sentence "
            f"inside <reply> too. Up to {MAX_OPTION_COUNT} options of at most "
            f"{OPTION_MAX_CHARS} characters each."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": f"The question, up to {QUESTION_MAX_CHARS} characters.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"{MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} different options.",
                },
                "multiple": {
                    "type": "boolean",
                    "description": "True to let each member pick several options.",
                },
            },
            "required": ["question", "options"],
        },
    }


def _results_definition() -> dict[str, Any]:
    return {
        "name": POLL_RESULTS_TOOL_NAME,
        "description": (
            "Read the count of a poll or a date poll: how many picked each option and who. "
            "Without poll_id it is the newest open poll. Report the result in your reply."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "poll_id": {"type": "string", "description": "Optional, like p1."},
            },
        },
    }


def _close_definition() -> dict[str, Any]:
    return {
        "name": CLOSE_POLL_TOOL_NAME,
        "description": (
            "Close a poll so it takes no more votes, and get its final count. Without poll_id "
            "it is the newest open poll. Use it when a member asks to close the vote."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "poll_id": {"type": "string", "description": "Optional, like p1."},
            },
        },
    }
