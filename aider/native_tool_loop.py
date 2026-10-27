"""Pure helpers for one round of the native tool-calling loop.
Given normalized ToolCalls, they build the assistant tool_calls message and one tool result message per call,
executing each call through a NativeToolRegistry.
Tool failures are reported back to the model as tool results instead of interrupting the conversation.
"""

from typing import Any, Optional

from aider.native_tool_calls import ToolCall, field
from aider.native_toolcalling import (
    NativeToolRegistry,
    ToolResult,
    make_tool_result_message,
)

# Upper bound on model -> tools -> model round trips for one user message.
MAX_TOOL_ROUNDS = 8
TOOL_ERROR_PREFIX = "Error: "
FINAL_ANSWER_CHOICE = "none"


def get_tool_calls(message: Optional[Any]) -> list[Any]:
    """Return the structured tool calls on a completion message, or an empty list."""
    return list(field(message, "tool_calls") or []) if message is not None else []


def assistant_tool_call_message(content: str, calls: list[ToolCall]) -> dict[str, Any]:
    """Echo the assistant turn that requested tools, in OpenAI message format."""
    return {
        "role": "assistant",
        "content": content,
        "tool_calls": [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": call.arguments},
            }
            for call in calls
        ],
    }


def execute_tool_call(registry: NativeToolRegistry, call: ToolCall) -> ToolResult:
    """Run one call; any failure becomes an error result the model can read."""
    try:
        return registry.execute(call)
    except Exception as err:  # tool handlers may raise anything; the model gets the message
        return ToolResult(
            tool_call_id=call.id,
            name=call.name,
            content=f"{TOOL_ERROR_PREFIX}{err}",
        )


def build_tool_round_messages(
    registry: NativeToolRegistry, content: str, calls: list[ToolCall]
) -> list[dict[str, Any]]:
    """Messages to append after a tool-calling turn: the turn itself, then each result."""
    results = [execute_tool_call(registry, call) for call in calls]
    return [assistant_tool_call_message(content, calls)] + [
        make_tool_result_message(result) for result in results
    ]
