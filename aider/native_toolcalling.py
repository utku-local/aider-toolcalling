"""Experimental native tool-calling helpers for Aider.

This module is deliberately isolated from Aider's existing edit pipeline.
It normalizes OpenAI-compatible tool-call responses and executes only
explicitly registered local Python functions.
"""

import json
from dataclasses import dataclass
from typing import Any, Callable

from aider.native_tool_calls import ToolCall
from aider.native_argument_repair import repair_arguments
from aider.native_tool_schema import coerce_integers, validate_arguments, wire_parameters


class NativeToolError(ValueError):
    """Raised when a tool call cannot be executed as requested."""


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
            raise NativeToolError(f"Invalid or duplicate tool name: {name!r}")

        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": parameters,
            },
        }
        self._tools[name] = (schema, handler)

    def without(self, *names: str) -> "NativeToolRegistry":
        """A new registry with the same tools except `names` (tools are shared, not copied)."""
        other = NativeToolRegistry()
        other._tools = {name: entry for name, entry in self._tools.items() if name not in names}
        return other

    def schemas(self) -> list[dict[str, Any]]:
        """Tool schemas as sent to the model (integer parameters shown as whole numbers)."""
        return [
            {**schema, "function": {**schema["function"], "parameters": wire_parameters(schema["function"]["parameters"])}}
            for schema, _ in self._tools.values()
        ]

    def execute(self, call: ToolCall) -> ToolResult:
        """Execute one registered, schema-valid tool call; never execute unknown names."""
        if call.name not in self._tools:
            raise NativeToolError(
                f"Tool is not registered: {call.name!r}; available tools: {sorted(self._tools)}"
            )

        try:
            arguments = json.loads(call.arguments)
        except json.JSONDecodeError as exc:
            raise NativeToolError(f"Invalid JSON arguments for tool {call.name!r}: {exc}") from exc

        if not isinstance(arguments, dict):
            raise NativeToolError("Tool arguments must be a JSON object")

        schema, handler = self._tools[call.name]
        parameters = schema["function"]["parameters"]
        arguments = coerce_integers(parameters, repair_arguments(parameters, arguments))
        problems = validate_arguments(parameters, arguments)
        if problems:
            raise NativeToolError(f"Invalid arguments for tool {call.name!r}: {'; '.join(problems)}")

        result = handler(**arguments)

        if isinstance(result, str):
            content = result
        else:
            content = json.dumps(result, ensure_ascii=False, default=str)

        return ToolResult(
            tool_call_id=call.id,
            name=call.name,
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
