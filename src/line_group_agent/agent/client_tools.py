"""The client tools of the agent, found by name.

Built by the service builder from the feature folders' tools; read by the model caller
(the definitions sent with each request) and by the answerer (running a call).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from line_group_agent.agent.client_tool import ClientTool, ToolOutcome, ToolTurn


class ClientTools:
    """A set of client tools keyed by name."""

    def __init__(self, tools: Iterable[ClientTool] = ()) -> None:
        self._tools: dict[str, ClientTool] = {}
        for tool in tools:
            self.add(tool)

    def add(self, tool: ClientTool) -> None:
        """Add a tool; a name that is already taken is a mistake of the builder."""
        if tool.name in self._tools:
            raise ValueError(f"two tools are named {tool.name}")
        self._tools[tool.name] = tool

    def definitions(self) -> list[dict[str, Any]]:
        """Return the tool objects for the API request, in the order they were added."""
        return [tool.definition for tool in self._tools.values()]

    def has(self, name: object) -> bool:
        """Whether a tool of this name is known."""
        return isinstance(name, str) and name in self._tools

    def run(self, name: str, tool_input: object, turn: ToolTurn) -> ToolOutcome:
        """Run the named tool (it must be known) and return its result."""
        return self._tools[name].run(tool_input, turn)
