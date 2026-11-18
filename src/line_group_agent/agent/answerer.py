"""Answer one mention inside the group's running conversation: add the turn, call the
Messages API, run the history-search and show-cards tools, and return the reply text
and the cards to send.

Called by the event dispatcher for each message that mentions the bot. The
conversation record, the context amount and the money counters are kept here and in
the objects it uses; rolling a full conversation over is the rollover's job.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from line_group_agent.agent.model_caller import ModelCaller
from line_group_agent.agent.prompt import (
    CARDS_SENT_RESULT,
    NO_VALID_CARDS_RESULT,
    SEARCH_HISTORY_TOOL_NAME,
    SHOW_CARDS_TOOL_NAME,
    build_envelope,
    extract_reply,
    format_search_results,
)
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


@dataclass(frozen=True)
class Answer:
    """What to send for one mention: a reply text, cards, both or neither."""

    text: str | None
    cards: list[Card] = field(default_factory=list)


class Answerer:
    """Turns a mention into at most one reply text and one set of cards."""

    def __init__(
        self,
        config: AgentConfig,
        caller: ModelCaller,
        group_log: GroupLog,
        conversations: GroupConversations,
        books: SpendBooks,
    ) -> None:
        self.config = config
        self.caller = caller
        self.group_log = group_log
        self.conversations = conversations
        self.books = books

    async def answer(self, group_id: str, mention: GroupMessage) -> Answer:
        """Return what to send for this mention; an answer with no text and no cards
        means send nothing. The cards are those of the last `show_cards` call.

        When the overall month or the group's month could not take the most this
        mention may cost, the API is not called and the configured budget text is
        returned.
        """
        conversation = self.conversations.get(group_id)
        async with conversation.lock:
            return await self._answer(conversation, mention)

    async def _answer(self, conversation: GroupConversation, mention: GroupMessage) -> Answer:
        group_id = conversation.group_id
        budget = self.config.budget
        estimate = mention_estimate_usd(self.config, context_tokens=conversation.context_tokens)
        if not self.books.can_afford(group_id, to_currency(estimate, budget)):
            logger.info("answer: budget left is below one mention; not calling the API")
            return Answer(budget.exhausted_text)

        envelope = self._envelope(conversation, mention)
        messages = pair_tool_calls([*conversation.history(), {"role": "user", "content": envelope}])
        conversation.add_user(envelope)
        conversation.last_turn_message_id = mention.message_id

        texts: list[str] = []
        cards: list[Card] = []
        for request_index in range(self.config.max_tool_rounds + 1):
            if request_index > 0 and not self._can_afford_request(conversation):
                logger.info("answer: budget left is below one request; stopping the tool loop")
                break
            answer = await self.caller.create(group_id, messages)
            if answer is None:
                break
            conversation.add_assistant(answer)
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
            results, shown = self._run_tools(group_id, content)
            if shown is not None:
                cards = shown
            messages.append({"role": "user", "content": results})
            conversation.add_user(results)

        return Answer(extract_reply("\n".join(texts)), cards)

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
        self, group_id: str, content: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[Card] | None]:
        """Run the client tools of one turn. Also return the cards of the last
        `show_cards` call that held a usable card, or None when there was none."""
        results: list[dict[str, Any]] = []
        shown: list[Card] | None = None
        for block in content:
            if block.get("type") != "tool_use":
                continue
            tool_input = block.get("input")
            if block.get("name") == SHOW_CARDS_TOOL_NAME:
                cards = parse_cards(tool_input)
                if cards:
                    shown = cards
                    results.append(_tool_result(block, CARDS_SENT_RESULT))
                else:
                    results.append(_tool_result(block, NO_VALID_CARDS_RESULT, is_error=True))
                continue
            query = tool_input.get("query") if isinstance(tool_input, dict) else None
            if block.get("name") != SEARCH_HISTORY_TOOL_NAME or not isinstance(query, str):
                results.append(_tool_result(block, "Unknown tool or missing query.", is_error=True))
                continue
            found = self.group_log.search(group_id, query, self.config.history_search_limit)
            results.append(_tool_result(block, format_search_results(found)))
        return results, shown


def _tool_result(block: dict[str, Any], content: str, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block["id"],
        "content": content,
    }
    if is_error:
        result["is_error"] = True
    return result
