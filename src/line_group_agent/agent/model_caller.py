"""One call to the Messages API for a group: the fixed request parts (model, system
text, tools, cache settings), the error handling and the cost counting.

Called by the answerer for each request of a mention and by the rollover for a
summary. The answer comes back as the plain dict the API sent, and is not recorded
here.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import anthropic

from line_group_agent.agent.prompt import search_history_tool, show_cards_tool
from line_group_agent.config.agent_config import AgentConfig
from line_group_agent.spend.pricing import to_currency, usage_cost_usd
from line_group_agent.spend.spend_books import SpendBooks

logger = logging.getLogger(__name__)


class MessagesClient(Protocol):
    """The part of the Anthropic client the caller uses (`client.messages`)."""

    @property
    def messages(self) -> Any: ...


class ModelCaller:
    """Sends a conversation to the model and counts what the answer cost."""

    def __init__(
        self,
        config: AgentConfig,
        client: MessagesClient,
        system_text: str,
        books: SpendBooks,
    ) -> None:
        self.config = config
        self.client = client
        self.system_text = system_text
        self.books = books
        self.tools = self._build_tools()
        # Prompt caching: one breakpoint after the fixed part (tools and system) and a
        # top-level one that moves to the end of each request, so a request reads
        # everything the earlier ones wrote.
        self._cache_control = {"type": "ephemeral", "ttl": config.cache_ttl}

    async def create(
        self,
        group_id: str,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None = None,
        tool_choice: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        """Send `messages` and return the answer, or None when the API refused or failed.

        The cost is added to the group's month and to the overall month.
        """
        request: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": max_tokens or self.config.max_tokens,
            "system": [
                {"type": "text", "text": self.system_text, "cache_control": self._cache_control}
            ],
            "messages": messages,
            "tools": self.tools,
            "output_config": {"effort": self.config.effort},
            "cache_control": self._cache_control,
        }
        if tool_choice is not None:
            request["tool_choice"] = tool_choice
        try:
            response = await self.client.messages.create(**request)
        except anthropic.APIStatusError as error:
            logger.warning("model: API refused the request (status %d)", error.status_code)
            return None
        except anthropic.APIError as error:
            logger.warning("model: API call failed (%s)", type(error).__name__)
            return None
        answer: dict[str, Any] = response.to_dict()
        cost = usage_cost_usd(
            answer.get("usage") or {}, self.config.prices, cache_ttl=self.config.cache_ttl
        )
        self.books.add(group_id, to_currency(cost, self.config.budget))
        return answer

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
