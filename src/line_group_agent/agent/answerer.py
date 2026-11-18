"""Answer one mention: call the Messages API, run the history-search tool, keep the
conversation record and the monthly spend, and return the text to send.

Called by the event dispatcher for each message that mentions the bot.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import anthropic

from line_group_agent.agent.prompt import (
    SEARCH_HISTORY_TOOL_NAME,
    build_envelope,
    extract_reply,
    format_search_results,
    search_history_tool,
)
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


class MessagesClient(Protocol):
    """The part of the Anthropic client the answerer uses (`client.messages`)."""

    @property
    def messages(self) -> Any: ...


class Answerer:
    """Turns a mention into at most one reply text."""

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

    async def answer(self, group_id: str, mention: GroupMessage) -> str | None:
        """Return the text to send for this mention, or None to send nothing.

        When this month's spend plus the most this mention may cost would pass the
        limit, the API is not called and the configured budget text is returned.
        """
        budget = self.config.budget
        if not self.ledger.can_afford(to_currency(mention_estimate_usd(self.config), budget)):
            logger.info("answer: budget left is below one mention; not calling the API")
            return budget.exhausted_text

        recent = self.group_log.list_recent(
            group_id, self.config.recent_message_count, exclude_message_id=mention.message_id
        )
        envelope = build_envelope(recent, mention)
        messages: list[dict[str, Any]] = [{"role": "user", "content": envelope}]
        self.conversation_log.add_user(envelope)

        texts: list[str] = []
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
            results = self._run_tools(group_id, content)
            messages.append({"role": "user", "content": results})
            self.conversation_log.add_user(results)

        return extract_reply("\n".join(texts))

    async def _create(self, messages: list[dict[str, Any]]) -> tuple[Any, dict[str, Any]] | None:
        try:
            response = await self.client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                system=self.system_text,
                messages=messages,
                tools=self._tools,
                output_config={"effort": self.config.effort},
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

    def _run_tools(self, group_id: str, content: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for block in content:
            if block.get("type") != "tool_use":
                continue
            query = (block.get("input") or {}).get("query")
            if block.get("name") != SEARCH_HISTORY_TOOL_NAME or not isinstance(query, str):
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": "Unknown tool or missing query.",
                        "is_error": True,
                    }
                )
                continue
            found = self.group_log.search(group_id, query, self.config.history_search_limit)
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": format_search_results(found),
                }
            )
        return results

    def _build_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = [search_history_tool(self.config.history_search_limit)]
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
