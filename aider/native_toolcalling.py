"""Experimental native tool-calling helpers for Aider.

This module is deliberately isolated from Aider's existing edit pipeline.
It normalizes OpenAI-compatible tool-call responses and executes only
explicitly registered local Python functions.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ToolResult:
    tool_call_id: str
    name: str
    content: str


class NativeToolRegistry:
    """Registry of explicitly allowed tools."""

    def __init__(self):
        self._tools: dict[str, tuple[dict[str, Any], Callable[..., Any]]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: Callable[..., Any],
    ) -> None:
        if not name or name in self._tools:
            raise ValueError(f"Invalid or duplicate tool name: {name!r}")

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._tools[name] = (schema, handler)

    def schemas(self) -> list[dict[str, Any]]:
        return [entry[0] for entry in self._tools.values()]

    def execute(self, tool_call: Any) -> ToolResult:
        """Execute one registered tool call; never execute unknown names."""
        function = getattr(tool_call, "function", None)
        call_id = getattr(tool_call, "id", None)
        if not function or not call_id:
            raise ValueError("Tool call is missing its function or call ID")

        name = getattr(function, "name", None)
        raw_arguments = getattr(function, "arguments", "{}")

        if name not in self._tools:
            raise ValueError(f"Tool is not registered: {name!r}")

        try:
            arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else raw_arguments
            )
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid JSON arguments for tool {name!r}") from exc

        if not isinstance(arguments, dict):
            raise ValueError("Tool arguments must be a JSON object")

        _, handler = self._tools[name]
        result = handler(**arguments)

        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, ensure_ascii=False, default=str)

        return ToolResult(
            tool_call_id=call_id,
            name=name,
            content=content,
        )


def make_tool_result_message(result: ToolResult) -> dict[str, Any]:
    """Format a result as an OpenAI-compatible conversation message."""
    return {
        "role": "tool",
        "tool_call_id": result.tool_call_id,
        "name": result.name,
        "content": result.content,
    }
