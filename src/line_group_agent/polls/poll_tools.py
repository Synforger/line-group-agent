"""The tools the model uses to run polls: make a poll or a date poll, read the count, close
one, and take back the vote of the member who asks.

A poll goes out as a card after the reply text; votes are counted by the agent without the
model (see the postback handler). A date poll is a poll whose options are candidate dates
and whose buttons switch "that day suits me" on and off. With a LIFF app configured the card
opens the voting page instead of carrying a button per option. Called by the service builder,
which adds the tools to the client tools.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from line_group_agent._common.one_line import one_line
from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn
from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.polls.poll import KIND_CHOICE, KIND_DATE, Poll
from line_group_agent.polls.poll_book import PollBook, VoteResult
from line_group_agent.polls.poll_message import (
    OPTION_MAX_CHARS,
    QUESTION_MAX_CHARS,
    build_poll_message,
)
from line_group_agent.polls.poll_text import format_poll_results, poll_record_line

CREATE_POLL_TOOL_NAME = "create_poll"
CREATE_DATE_POLL_TOOL_NAME = "create_date_poll"
POLL_RESULTS_TOOL_NAME = "poll_results"
CLOSE_POLL_TOOL_NAME = "close_poll"
WITHDRAW_VOTE_TOOL_NAME = "withdraw_vote"
MIN_OPTION_COUNT = 2
MAX_OPTION_COUNT = 10
NO_ROOM_RESULT = "This reply already holds as many extra messages as LINE allows. Nothing was made."
NO_POLL_RESULT = "There is no such poll in this group."
CLOSED_POLL_RESULT = "That poll is closed, so votes can no longer change."
UNKNOWN_MEMBER_RESULT = "The member who asked cannot be identified, so no vote was taken back."
NO_VOTE_RESULT = "That member has no vote in the poll, so nothing was taken back."
NO_TEST_POLL_SENTENCE = "Do not make a poll to test the tools."
BAD_OPTIONS_RESULT = (
    f"Give a question and {MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} different, non-empty options."
)
BAD_DATES_RESULT = (
    f"Give a title and {MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} different, non-empty dates."
)


def poll_tools(book: PollBook, *, liff_id: str | None = None) -> list[ClientTool]:
    """Return the poll tools, working on `book`. With `liff_id` the poll cards open the voting
    page of that LIFF app."""

    def make(
        turn: ToolTurn, question: str, labels: list[str] | None, kind: str, *, multiple: bool
    ) -> ToolOutcome:
        if not question or labels is None:
            return ToolOutcome(BAD_DATES_RESULT if kind == KIND_DATE else BAD_OPTIONS_RESULT, True)
        if not turn.output.has_room():
            return ToolOutcome(NO_ROOM_RESULT, is_error=True)
        poll = book.create(turn.group_id, question, labels, kind=kind, multiple=multiple)
        turn.output.add(_extra_of(poll, liff_id))
        return ToolOutcome(
            f"Poll {poll.id} is sent as a card after your reply. Members vote from it; "
            "votes are counted without you, so call poll_results when someone asks for the count."
        )

    def create(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        return make(
            turn,
            one_line(fields.get("question"), QUESTION_MAX_CHARS),
            clean_labels(fields.get("options")),
            KIND_CHOICE,
            multiple=fields.get("multiple") is True,
        )

    def create_date(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        fields = tool_input if isinstance(tool_input, dict) else {}
        return make(
            turn,
            one_line(fields.get("title"), QUESTION_MAX_CHARS),
            clean_labels(fields.get("dates")),
            KIND_DATE,
            multiple=True,
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
        result = f"Poll {poll.id} is closed. Final count:\n{format_poll_results(poll)}"
        if _drop_card_of(poll, turn.output):
            result += "\nIts card was made in this same reply, so it is not sent."
        return ToolOutcome(result)

    def withdraw(tool_input: object, turn: ToolTurn) -> ToolOutcome:
        poll = book.get(turn.group_id, _poll_id_of(tool_input))
        if poll is None:
            return ToolOutcome(NO_POLL_RESULT, is_error=True)
        if poll.is_closed:
            return ToolOutcome(CLOSED_POLL_RESULT, is_error=True)
        user_id = turn.mention.user_id
        if user_id is None:
            return ToolOutcome(UNKNOWN_MEMBER_RESULT, is_error=True)
        if book.withdraw(turn.group_id, poll.id, user_id) is not VoteResult.WITHDRAWN:
            return ToolOutcome(NO_VOTE_RESULT, is_error=True)
        return ToolOutcome(f"The vote of the member who asked is taken back from poll {poll.id}.")

    return [
        ClientTool(CREATE_POLL_TOOL_NAME, _create_definition(), create),
        ClientTool(CREATE_DATE_POLL_TOOL_NAME, _create_date_definition(), create_date),
        ClientTool(POLL_RESULTS_TOOL_NAME, _results_definition(), results),
        ClientTool(CLOSE_POLL_TOOL_NAME, _close_definition(), close),
        ClientTool(WITHDRAW_VOTE_TOOL_NAME, _withdraw_definition(), withdraw),
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


def _extra_of(poll: Poll, liff_id: str | None) -> OutgoingExtra:
    return OutgoingExtra(build_poll_message(poll, liff_id=liff_id), poll_record_line(poll))


def _drop_card_of(poll: Poll, output: TurnOutput) -> bool:
    """Take the card of `poll` out of the reply when this turn made it (a poll made and closed
    in the same reply has nothing left to vote on). Return whether a card was taken out."""
    record_line = poll_record_line(poll)
    kept = [extra for extra in output.extras if extra.record_line != record_line]
    is_dropped = len(kept) < len(output.extras)
    output.extras[:] = kept
    return is_dropped


def _poll_id_of(tool_input: object) -> str | None:
    poll_id = tool_input.get("poll_id") if isinstance(tool_input, dict) else None
    return poll_id if isinstance(poll_id, str) and poll_id.strip() else None


def _create_definition() -> dict[str, Any]:
    return {
        "name": CREATE_POLL_TOOL_NAME,
        "description": (
            "Start a vote in the group. It is sent as a card after your reply; members vote "
            "from it by pressing an option's button or the button that opens the voting page, "
            "one vote each (or several with multiple). Picking the option already picked "
            "changes nothing in a one-vote poll; a member takes a vote back by asking you "
            "(withdraw_vote). Use it when a member asks for a vote. "
            f"{NO_TEST_POLL_SENTENCE} Write a short sentence "
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


def _create_date_definition() -> dict[str, Any]:
    return {
        "name": CREATE_DATE_POLL_TOOL_NAME,
        "description": (
            "Find a date that suits everyone. It is sent as a card after your reply, with a "
            "button per candidate date or one that opens the voting page; a member marks every "
            "date that suits them, and marks again to take it back. Use it when members need "
            "to agree on a date. poll_results then gives each date's count and names. "
            f"{NO_TEST_POLL_SENTENCE} Write a short sentence "
            f"inside <reply> too. Up to {MAX_OPTION_COUNT} dates of at most "
            f"{OPTION_MAX_CHARS} characters each, like 11/23(Sat)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": f"What it is for, up to {QUESTION_MAX_CHARS} characters.",
                },
                "dates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": f"{MIN_OPTION_COUNT} to {MAX_OPTION_COUNT} different dates.",
                },
            },
            "required": ["title", "dates"],
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


def _withdraw_definition() -> dict[str, Any]:
    return {
        "name": WITHDRAW_VOTE_TOOL_NAME,
        "description": (
            "Take back the vote of the member whose message you are answering: every option "
            "they picked in the poll. Use it when a member asks to cancel or remove their own "
            "vote; it cannot touch anyone else's. Without poll_id it is the newest open poll. "
            "A member who only wants another option presses that button instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "poll_id": {"type": "string", "description": "Optional, like p1."},
            },
        },
    }
