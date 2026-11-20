"""Answer one mention inside the group's running conversation: add the turn, call the
Messages API, run the history-search, show-cards, delete-messages and group tools, and
return the reply text, the cards, the extra messages and the quick replies to send.

Called by the event dispatcher for each message that mentions or calls the bot, and for a
message that only holds its name, which the model may leave unanswered. The
conversation record, the context amount and the money counters are kept here and in
the objects it uses; rolling a full conversation over is the rollover's job.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from line_group_agent.agent.client_tool import ToolOutcome, ToolTurn
from line_group_agent.agent.client_tools import ClientTools
from line_group_agent.agent.message_deleter import MessageDeleter
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import (
    CARDS_SENT_RESULT,
    DELETE_MESSAGES_TOOL_NAME,
    NO_VALID_CARDS_RESULT,
    NOTHING_DELETED_RESULT,
    REPLY_PATTERN,
    REPLY_RETRY_REQUEST,
    SEARCH_HISTORY_TOOL_NAME,
    SHOW_CARDS_TOOL_NAME,
    STAY_SILENT_REFUSED_RESULT,
    STAY_SILENT_RESULT,
    STAY_SILENT_SKIPPED_RESULT,
    STAY_SILENT_TOOL_NAME,
    build_envelope,
    build_user_content,
    extract_reply,
    format_search_results,
)
from line_group_agent.agent.slow_answer import is_slow_ahead
from line_group_agent.agent.thinking_blocks import without_thinking
from line_group_agent.agent.tool_pairing import pair_tool_calls
from line_group_agent.agent.turn_output import TurnOutput
from line_group_agent.cards.card import Card
from line_group_agent.cards.card_image_finder import CardImageFinder
from line_group_agent.cards.card_input import parse_cards
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.line_api.outgoing_extra import OutgoingExtra
from line_group_agent.line_api.quick_reply import QuickReplyItem
from line_group_agent.media.photo_picker import PhotoPicker
from line_group_agent.records.group_conversation import GroupConversation
from line_group_agent.records.group_conversations import GroupConversations
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.spend.pricing import (
    mention_estimate_usd,
    request_estimate_usd,
    to_currency,
)
from line_group_agent.spend.spend_books import SpendBooks

logger = logging.getLogger(__name__)

SlowNotice = Callable[[], Awaitable[None]]
TOOL_FAILED_RESULT = "The tool failed and did nothing. Tell the group briefly, or try again."


@dataclass(frozen=True)
class Answer:
    """What to send for one mention: a reply text, cards, extra messages (a poll card, a
    location) and quick reply buttons, or none of them."""

    text: str | None
    cards: list[Card] = field(default_factory=list)
    extras: list[OutgoingExtra] = field(default_factory=list)
    quick_replies: list[QuickReplyItem] = field(default_factory=list)
    # False for a notice sent without taking a turn (the budget text): recording it as
    # the bot's reply would move the "since your last turn" window past messages the
    # model has not seen yet.
    record: bool = True


class Answerer:
    """Turns a mention into at most one reply text and one set of cards."""

    def __init__(
        self,
        config: AgentConfig,
        caller: ModelCaller,
        group_log: GroupLog,
        conversations: GroupConversations,
        books: SpendBooks,
        deleter: MessageDeleter,
        *,
        client_tools: ClientTools | None = None,
        photos: PhotoPicker | None = None,
        card_images: CardImageFinder | None = None,
    ) -> None:
        self.config = config
        self.caller = caller
        self.group_log = group_log
        self.conversations = conversations
        self.books = books
        self.deleter = deleter
        self.client_tools = client_tools or ClientTools()
        self.photos = photos
        self.card_images = card_images

    async def answer(
        self,
        group_id: str,
        mention: GroupMessage,
        *,
        on_slow: SlowNotice | None = None,
        is_name_only: bool = False,
    ) -> Answer:
        """Return what to send for this mention; an answer with no text and no cards
        means send nothing. The cards are those of the last `show_cards` call; a card without
        a picture is given the one its page names, when the card image finder is set.

        With `is_name_only`, the message only holds the bot's name: the model is told it
        may not be addressed to it, and may end the turn with `stay_silent` (nothing is
        sent; the turn stays in the conversation).

        When the overall month or the group's month could not take the most this
        mention may cost, the API is not called and the configured budget text is
        returned. When a reply could not be made for any other reason than the API
        failing, the configured error text is returned. `on_slow` is awaited once,
        right after the first request, if that request stopped in the middle of web
        work that goes on.
        """
        conversation = self.conversations.get(group_id)
        async with conversation.lock:
            return await self._answer(conversation, mention, on_slow, is_name_only)

    async def _answer(
        self,
        conversation: GroupConversation,
        mention: GroupMessage,
        on_slow: SlowNotice | None,
        is_name_only: bool,
    ) -> Answer:
        group_id = conversation.group_id
        budget = self.config.budget
        estimate = mention_estimate_usd(self.config, context_tokens=conversation.context_tokens)
        if not self.books.can_afford(group_id, to_currency(estimate, budget)):
            logger.info("answer: budget left is below one mention; not calling the API")
            return Answer(budget.exhausted_text, record=False)

        turn = self._user_turn(conversation, mention, is_name_only)
        # Thinking of earlier turns is left out of the request (see `thinking_blocks`); the
        # blocks of this turn's own tool rounds are added below and stay.
        history = without_thinking(conversation.history())
        messages = pair_tool_calls([*history, {"role": "user", "content": turn}])
        conversation.add_user(turn)
        conversation.last_turn_message_id = mention.message_id

        texts: list[str] = []
        cards: list[Card] = []
        output = TurnOutput()
        is_api_down = is_over_budget = False
        last_answer: dict[str, Any] = {}
        for request_index in range(self.config.max_tool_rounds + 1):
            if request_index > 0 and not self._can_afford_request(conversation):
                logger.info("answer: budget left is below one request; stopping the tool loop")
                is_over_budget = True
                break
            answer = await self.caller.create(group_id, messages)
            if answer is None:
                is_api_down = True
                break
            conversation.add_assistant(answer)
            last_answer = answer
            if request_index == 0 and on_slow is not None and is_slow_ahead(answer):
                await on_slow()
            content = answer.get("content") or []
            if is_name_only and _calls_stay_silent(content):
                # The turn is kept whole (its call has a result) and nothing is sent.
                conversation.add_user(_silence_results(content))
                logger.info("answer: stayed silent for a message that only held the name")
                return Answer(None)
            if text := _text_of(answer):
                texts.append(text)
            # The answer's blocks go back to the API exactly as they came (thinking
            # signatures included).
            messages.append({"role": "assistant", "content": content})

            stop_reason = answer.get("stop_reason")
            if stop_reason == "pause_turn":
                continue
            if stop_reason != "tool_use":
                break
            if request_index == self.config.max_tool_rounds:
                logger.info("answer: tool rounds used up (%d)", self.config.max_tool_rounds)
                break
            results, shown = self._run_tools(conversation, mention, content, output)
            if shown is not None:
                cards = shown
            messages.append({"role": "user", "content": results})
            conversation.add_user(results)

        reply = extract_reply("\n".join(texts))
        if (
            reply is None
            and not is_api_down
            and not is_over_budget
            and _forgot_reply_tags(last_answer)
        ):
            reply, is_api_down, is_over_budget = await self._ask_for_reply_again(
                conversation, messages
            )
        if reply is None and not cards and not output.extras:
            return self._answer_without_reply(
                is_api_down=is_api_down, is_over_budget=is_over_budget, is_name_only=is_name_only
            )
        if cards and self.card_images is not None:
            cards = await self.card_images.fill(cards)
        return Answer(reply, cards, extras=output.extras, quick_replies=output.quick_replies)

    async def _ask_for_reply_again(
        self, conversation: GroupConversation, messages: list[dict[str, Any]]
    ) -> tuple[str | None, bool, bool]:
        """Ask once, as a continuation of the same turn, for the answer to be written again
        inside `<reply>`. Return the reply found in the new answer (None when it has none),
        then whether the API was down and whether the budget could not take the request."""
        if not self._can_afford_request(conversation):
            logger.info("answer: budget left is below one request; not asking for the reply again")
            return None, False, True
        logger.info("answer: the answer had no <reply>; asking once more")
        messages.append({"role": "user", "content": REPLY_RETRY_REQUEST})
        conversation.add_user(REPLY_RETRY_REQUEST)
        answer = await self.caller.create(conversation.group_id, messages)
        if answer is None:
            return None, True, False
        conversation.add_assistant(answer)
        return extract_reply(_text_of(answer)), False, False

    def _answer_without_reply(
        self, *, is_api_down: bool, is_over_budget: bool, is_name_only: bool
    ) -> Answer:
        if is_api_down:
            return Answer(None)
        if is_over_budget:
            return Answer(self.config.budget.exhausted_text)
        if is_name_only:
            # A message that only held the name may not have been meant for the bot.
            return Answer(None)
        return Answer(self.config.error_text or None)

    def _user_turn(
        self, conversation: GroupConversation, mention: GroupMessage, is_name_only: bool
    ) -> str | list[dict[str, Any]]:
        """Return the user turn for this mention: the envelope, with the photos sent since
        the bot's last turn attached when photos are read."""
        group_id = conversation.group_id
        since = self._since_last_turn(conversation, mention)
        if conversation.starts_new_generation:
            recent = self.group_log.list_recent(
                group_id, self.config.recent_message_count, exclude_message_id=mention.message_id
            )
            envelope = build_envelope(
                recent, mention, summary=conversation.pending_summary, is_name_only=is_name_only
            )
        else:
            envelope = build_envelope(since, mention, is_name_only=is_name_only)
        if self.photos is None:
            return envelope
        return build_user_content(envelope, self.photos.pick(group_id, since))

    def _since_last_turn(
        self, conversation: GroupConversation, mention: GroupMessage
    ) -> list[GroupMessage]:
        # A turn that opens a generation shows the recent messages instead, and needs this
        # list only to find the photos.
        if conversation.starts_new_generation and self.photos is None:
            return []
        return self.group_log.list_since_turn(
            conversation.group_id,
            self.config.max_catch_up_messages,
            after_message_id=conversation.last_turn_message_id,
            exclude_message_id=mention.message_id,
        )

    def _can_afford_request(self, conversation: GroupConversation) -> bool:
        estimate = request_estimate_usd(self.config, context_tokens=conversation.context_tokens)
        return self.books.can_afford(
            conversation.group_id, to_currency(estimate, self.config.budget)
        )

    def _run_tools(
        self,
        conversation: GroupConversation,
        mention: GroupMessage,
        content: list[dict[str, Any]],
        output: TurnOutput,
    ) -> tuple[list[dict[str, Any]], list[Card] | None]:
        """Run the client tools of one turn. Also return the cards of the last
        `show_cards` call that held a usable card, or None when there was none. The group
        tools add their messages and quick replies to `output`."""
        results: list[dict[str, Any]] = []
        shown: list[Card] | None = None
        for block in content:
            if block.get("type") != "tool_use":
                continue
            if block.get("name") == STAY_SILENT_TOOL_NAME:
                results.append(_tool_result(block, STAY_SILENT_REFUSED_RESULT, is_error=True))
                continue
            if block.get("name") == SHOW_CARDS_TOOL_NAME:
                cards = parse_cards(block.get("input"))
                if cards:
                    shown = cards
                    results.append(_tool_result(block, CARDS_SENT_RESULT))
                else:
                    results.append(_tool_result(block, NO_VALID_CARDS_RESULT, is_error=True))
                continue
            name = block.get("name")
            if self.client_tools.has(name):
                turn = ToolTurn(conversation.group_id, mention, output)
                outcome = self._run_client_tool(str(name), block.get("input"), turn)
                results.append(_tool_result(block, outcome.content, is_error=outcome.is_error))
                continue
            results.append(self._run_query_tool(conversation, mention, block))
        return results, shown

    def _run_client_tool(self, name: str, tool_input: object, turn: ToolTurn) -> ToolOutcome:
        """Run a group tool; a tool that fails (a file that cannot be written) gives the model
        an error result instead of ending the whole answer."""
        try:
            return self.client_tools.run(name, tool_input, turn)
        except Exception as error:
            logger.error("answer: tool %s failed (%s)", name, type(error).__name__)
            return ToolOutcome(TOOL_FAILED_RESULT, is_error=True)

    def _run_query_tool(
        self, conversation: GroupConversation, mention: GroupMessage, block: dict[str, Any]
    ) -> dict[str, Any]:
        tool_input = block.get("input")
        query = tool_input.get("query") if isinstance(tool_input, dict) else None
        name = block.get("name")
        if name not in (SEARCH_HISTORY_TOOL_NAME, DELETE_MESSAGES_TOOL_NAME) or not isinstance(
            query, str
        ):
            return _tool_result(block, "Unknown tool or missing query.", is_error=True)
        group_id = conversation.group_id
        if name == SEARCH_HISTORY_TOOL_NAME:
            found = self.group_log.search(group_id, query, self.config.history_search_limit)
            return _tool_result(block, format_search_results(found))
        deleted = self.deleter.delete_matching(
            group_id,
            query,
            requester_user_id=mention.user_id,
            request_message_id=mention.message_id,
        )
        if deleted == 0:
            return _tool_result(block, NOTHING_DELETED_RESULT)
        return _tool_result(block, f"Deleted {deleted} message(s) from the records.")


def _text_of(answer: dict[str, Any]) -> str:
    """Return the text of one answer. Its text blocks are pieces of one text (a cited answer
    comes in many small ones, split mid-sentence), so they are joined with nothing between."""
    content = answer.get("content") or []
    return "".join(b["text"] for b in content if b.get("type") == "text")


def _forgot_reply_tags(answer: dict[str, Any]) -> bool:
    """Whether the answer that ended the turn wrote text but no `<reply>` at all."""
    if answer.get("stop_reason") != "end_turn":
        return False
    text = _text_of(answer)
    return bool(text.strip()) and REPLY_PATTERN.search(text) is None


def _calls_stay_silent(content: list[dict[str, Any]]) -> bool:
    return any(
        block.get("type") == "tool_use" and block.get("name") == STAY_SILENT_TOOL_NAME
        for block in content
    )


def _silence_results(content: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the results of a turn that ended in `stay_silent`: the call is accepted and
    any other call of the turn is not run."""
    return [
        _tool_result(block, STAY_SILENT_RESULT)
        if block.get("name") == STAY_SILENT_TOOL_NAME
        else _tool_result(block, STAY_SILENT_SKIPPED_RESULT, is_error=True)
        for block in content
        if block.get("type") == "tool_use"
    ]


def _tool_result(block: dict[str, Any], content: str, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block["id"],
        "content": content,
    }
    if is_error:
        result["is_error"] = True
    return result
