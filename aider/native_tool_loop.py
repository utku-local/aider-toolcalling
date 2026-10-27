"""Pure helpers for one round of the native tool-calling loop.
Given the assistant message of a completion, they build the assistant tool_calls message and one tool result
message per call, executing each call through a NativeToolRegistry.
Tool failures are reported back to the model as tool results instead of interrupting the conversation.
"""

from typing import Any, Optional

from aider.native_toolcalling import (
    NativeToolRegistry,
    ToolResult,
    make_tool_result_message,
)

# Upper bound on model -> tools -> model round trips for one user message.
MAX_TOOL_ROUNDS = 8
TOOL_ERROR_PREFIX = "Error: "
UNKNOWN_TOOL_NAME = "unknown"


def get_tool_calls(message: Optional[Any]) -> list[Any]:
    """Return the tool calls on a completion message, or an empty list."""
    return list(getattr(message, "tool_calls", None) or [])


def tool_call_name(tool_call: Any) -> str:
    function = getattr(tool_call, "function", None)
    return getattr(function, "name", None) or UNKNOWN_TOOL_NAME


def assistant_tool_call_message(message: Any) -> dict[str, Any]:
    """Echo the assistant turn that requested tools, in OpenAI message format."""
    return {
        "role": "assistant",
        "content": getattr(message, "content", None) or "",
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {
                    "name": tool_call_name(call),
                    "arguments": getattr(call.function, "arguments", None) or "{}",
                },
            }
            for call in get_tool_calls(message)
        ],
    }


def execute_tool_call(registry: NativeToolRegistry, tool_call: Any) -> ToolResult:
    """Run one call; any failure becomes an error result the model can read."""
    try:
        return registry.execute(tool_call)
    except Exception as err:  # tool handlers may raise anything; the model gets the message
        return ToolResult(
            tool_call_id=getattr(tool_call, "id", None) or "",
            name=tool_call_name(tool_call),
            content=f"{TOOL_ERROR_PREFIX}{err}",
        )


def build_tool_round_messages(registry: NativeToolRegistry, message: Any) -> list[dict[str, Any]]:
    """Messages to append after a tool-calling turn: the turn itself, then each result."""
    results = [execute_tool_call(registry, call) for call in get_tool_calls(message)]
    return [assistant_tool_call_message(message)] + [
        make_tool_result_message(result) for result in results
    ]
