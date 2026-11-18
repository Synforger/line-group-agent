"""Answer one mention: call the Messages API, run the history-search and show-cards
tools, keep the conversation record and the monthly spend, and return the reply text
and the cards to send.

Called by the event dispatcher for each message that mentions the bot.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import anthropic

from line_group_agent.agent.prompt import (
    CARDS_SENT_RESULT,
    NO_VALID_CARDS_RESULT,
    SEARCH_HISTORY_TOOL_NAME,
    SHOW_CARDS_TOOL_NAME,
    build_envelope,
    extract_reply,
    format_search_results,
    search_history_tool,
    show_cards_tool,
)
from line_group_agent.cards.card import Card
from line_group_agent.cards.card_input import parse_cards
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.records.conversation_log import ConversationLog
from line_group_agent.records.group_log import GroupLog, GroupMessage
from line_group_agent.spend.pricing import (
    mention_estimate_usd,
    request_estimate_usd,
    to_currency,
    usage_cost_usd,
)
from line_group_agent.spend.spend_ledger import SpendLedger

logger = logging.getLogger(__name__)

# Prompt caching: a breakpoint after the fixed part (tools and system) is reused across
# mentions; the top-level one moves to the end of each request, so the requests of one
# mention's tool loop reread the whole earlier prefix from the cache.
EPHEMERAL_CACHE = {"type": "ephemeral"}


class MessagesClient(Protocol):
    """The part of the Anthropic client the answerer uses (`client.messages`)."""

    @property
    def messages(self) -> Any: ...


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
        client: MessagesClient,
        system_text: str,
        group_log: GroupLog,
        conversation_log: ConversationLog,
        ledger: SpendLedger,
    ) -> None:
        self.config = config
        self.client = client
        self.system_text = system_text
        self.group_log = group_log
        self.conversation_log = conversation_log
        self.ledger = ledger
        self._tools = self._build_tools()

    async def answer(self, group_id: str, mention: GroupMessage) -> Answer:
        """Return what to send for this mention; an answer with no text and no cards
        means send nothing. The cards are those of the last `show_cards` call.

        When this month's spend plus the most this mention may cost would pass the
        limit, the API is not called and the configured budget text is returned.
        """
        budget = self.config.budget
        if not self.ledger.can_afford(to_currency(mention_estimate_usd(self.config), budget)):
            logger.info("answer: budget left is below one mention; not calling the API")
            return Answer(budget.exhausted_text)

        recent = self.group_log.list_recent(
            group_id, self.config.recent_message_count, exclude_message_id=mention.message_id
        )
        envelope = build_envelope(recent, mention)
        messages: list[dict[str, Any]] = [{"role": "user", "content": envelope}]
        self.conversation_log.add_user(envelope)

        texts: list[str] = []
        cards: list[Card] = []
        request_estimate = to_currency(request_estimate_usd(self.config), budget)
        for request_index in range(self.config.max_tool_rounds + 1):
            if request_index > 0 and not self.ledger.can_afford(request_estimate):
                logger.info("answer: budget left is below one request; stopping the tool loop")
                break
            created = await self._create(messages)
            if created is None:
                break
            response, answer = created
            content = answer.get("content") or []
            texts.extend(b["text"] for b in content if b.get("type") == "text")
            # The SDK's own blocks go back to the API unchanged (thinking signatures
            # included); the dict copy is only for reading and for the record.
            messages.append({"role": "assistant", "content": response.content})

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
            self.conversation_log.add_user(results)

        return Answer(extract_reply("\n".join(texts)), cards)

    async def _create(self, messages: list[dict[str, Any]]) -> tuple[Any, dict[str, Any]] | None:
        try:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=[
                    {"type": "text", "text": self.system_text, "cache_control": EPHEMERAL_CACHE}
                ],
                messages=messages,
                tools=self._tools,
                output_config={"effort": self.config.effort},
                cache_control=EPHEMERAL_CACHE,
            )
        except anthropic.APIStatusError as error:
            logger.warning("answer: API refused the request (status %d)", error.status_code)
            return None
        except anthropic.APIError as error:
            logger.warning("answer: API call failed (%s)", type(error).__name__)
            return None
        answer = response.to_dict()
        self.conversation_log.add_assistant(answer)
        cost = to_currency(
            usage_cost_usd(answer.get("usage") or {}, self.config.prices), self.config.budget
        )
        self.ledger.add(cost)
        return response, answer

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

    def _build_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [
            search_history_tool(self.config.history_search_limit),
            show_cards_tool(),
        ]
        search = self.config.web_search
        if search is not None:
            tools.append({"type": search.type, "name": "web_search", "max_uses": search.max_uses})
        fetch = self.config.web_fetch
        if fetch is not None:
            tool: dict[str, Any] = {
                "type": fetch.type,
                "name": "web_fetch",
                "max_uses": fetch.max_uses,
            }
            if fetch.max_content_tokens is not None:
                tool["max_content_tokens"] = fetch.max_content_tokens
            tools.append(tool)
        return tools


def _tool_result(block: dict[str, Any], content: str, *, is_error: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "tool_result",
        "tool_use_id": block["id"],
        "content": content,
    }
    if is_error:
        result["is_error"] = True
    return result
