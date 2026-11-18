"""Answer one mention inside the group's running conversation: add the turn, call the
Messages API, run the history-search, show-cards and delete-messages tools, and return
the reply text and the cards to send.

Called by the event dispatcher for each message that mentions the bot. The
conversation record, the context amount and the money counters are kept here and in
the objects it uses; rolling a full conversation over is the rollover's job.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from line_group_agent.agent.message_deleter import MessageDeleter
from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import (
    CARDS_SENT_RESULT,
    DELETE_MESSAGES_TOOL_NAME,
    NO_VALID_CARDS_RESULT,
    NOTHING_DELETED_RESULT,
    SEARCH_HISTORY_TOOL_NAME,
    SHOW_CARDS_TOOL_NAME,
    build_envelope,
    extract_reply,
    format_search_results,
)
from line_group_agent.agent.slow_answer import is_slow_ahead
from line_group_agent.agent.tool_pairing import pair_tool_calls
from line_group_agent.cards.card import Card
from line_group_agent.cards.card_input import parse_cards
from line_group_agent.config.agent_config import AgentConfig
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


@dataclass(frozen=True)
class Answer:
    """What to send for one mention: a reply text, cards, both or neither."""

    text: str | None
    cards: list[Card] = field(default_factory=list)
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
    ) -> None:
        self.config = config
        self.caller = caller
        self.group_log = group_log
        self.conversations = conversations
        self.books = books
        self.deleter = deleter

    async def answer(
        self, group_id: str, mention: GroupMessage, *, on_slow: SlowNotice | None = None
    ) -> Answer:
        """Return what to send for this mention; an answer with no text and no cards
        means send nothing. The cards are those of the last `show_cards` call.

        When the overall month or the group's month could not take the most this
        mention may cost, the API is not called and the configured budget text is
        returned. When a reply could not be made for any other reason than the API
        failing, the configured error text is returned. `on_slow` is awaited once,
        right after the first request, if that request stopped in the middle of web
        work that goes on.
        """
        conversation = self.conversations.get(group_id)
        async with conversation.lock:
            return await self._answer(conversation, mention, on_slow)

    async def _answer(
        self, conversation: GroupConversation, mention: GroupMessage, on_slow: SlowNotice | None
    ) -> Answer:
        group_id = conversation.group_id
        budget = self.config.budget
        estimate = mention_estimate_usd(self.config, context_tokens=conversation.context_tokens)
        if not self.books.can_afford(group_id, to_currency(estimate, budget)):
            logger.info("answer: budget left is below one mention; not calling the API")
            return Answer(budget.exhausted_text, record=False)

        envelope = self._envelope(conversation, mention)
        messages = pair_tool_calls([*conversation.history(), {"role": "user", "content": envelope}])
        conversation.add_user(envelope)
        conversation.last_turn_message_id = mention.message_id

        texts: list[str] = []
        cards: list[Card] = []
        is_api_down = is_over_budget = False
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
            if request_index == 0 and on_slow is not None and is_slow_ahead(answer):
                await on_slow()
            content = answer.get("content") or []
            texts.extend(b["text"] for b in content if b.get("type") == "text")
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
            results, shown = self._run_tools(conversation, mention, content)
            if shown is not None:
                cards = shown
            messages.append({"role": "user", "content": results})
            conversation.add_user(results)

        reply = extract_reply("\n".join(texts))
        if reply is None and not cards:
            return self._answer_without_reply(
                is_api_down=is_api_down, is_over_budget=is_over_budget
            )
        return Answer(reply, cards)

    def _answer_without_reply(self, *, is_api_down: bool, is_over_budget: bool) -> Answer:
        if is_api_down:
            return Answer(None)
        if is_over_budget:
            return Answer(self.config.budget.exhausted_text)
        return Answer(self.config.error_text or None)

    def _envelope(self, conversation: GroupConversation, mention: GroupMessage) -> str:
        group_id = conversation.group_id
        if conversation.starts_new_generation:
            recent = self.group_log.list_recent(
                group_id, self.config.recent_message_count, exclude_message_id=mention.message_id
            )
            return build_envelope(recent, mention, summary=conversation.pending_summary)
        since = self.group_log.list_since_turn(
            group_id,
            self.config.max_catch_up_messages,
            after_message_id=conversation.last_turn_message_id,
            exclude_message_id=mention.message_id,
        )
        return build_envelope(since, mention)

    def _can_afford_request(self, conversation: GroupConversation) -> bool:
        estimate = request_estimate_usd(self.config, context_tokens=conversation.context_tokens)
        return self.books.can_afford(
            conversation.group_id, to_currency(estimate, self.config.budget)
        )

    def _run_tools(
        self, conversation: GroupConversation, mention: GroupMessage, content: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[Card] | None]:
        """Run the client tools of one turn. Also return the cards of the last
        `show_cards` call that held a usable card, or None when there was none."""
        results: list[dict[str, Any]] = []
        shown: list[Card] | None = None
        for block in content:
            if block.get("type") != "tool_use":
                continue
            if block.get("name") == SHOW_CARDS_TOOL_NAME:
                cards = parse_cards(block.get("input"))
                if cards:
                    shown = cards
                    results.append(_tool_result(block, CARDS_SENT_RESULT))
                else:
                    results.append(_tool_result(block, NO_VALID_CARDS_RESULT, is_error=True))
                continue
            results.append(self._run_query_tool(conversation, mention, block))
        return results, shown

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


def _tool_result(block: dict[str, Any], content: str, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block["id"],
        "content": content,
    }
    if is_error:
        result["is_error"] = True
    return result
