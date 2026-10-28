"""Pure helpers for one round of the native tool-calling loop.
Given normalized ToolCalls, they build the assistant tool_calls message and one tool result message per call,
executing each call through a NativeToolRegistry.
Tool failures are reported back to the model as tool results instead of interrupting the conversation.
"""

from typing import Any, Optional

from aider.native_tool_calls import ToolCall, field
from aider.native_tool_ledger import OperationLedger
from aider.native_toolcalling import (
    NativeToolRegistry,
    ToolResult,
    make_tool_result_message,
)

# Default budget of model -> tools -> model round trips per user message (--max-tool-rounds).
DEFAULT_MAX_TOOL_ROUNDS = 25
TOOL_ERROR_PREFIX = "Error: "
FINAL_ANSWER_CHOICE = "none"
MAX_TOOL_RESULT_CHARS = 30_000
RESULT_TRUNCATED = "\n[result truncated to {limit} characters; request a smaller range or a narrower search]"
INTERRUPTED_RESULT = "Error: interrupted by the user before the tool finished"
REPEAT_HINT_TOOLS = frozenset({"read_file", "list_files", "find_files", "search_code", "find_symbol", "git"})
REPEAT_NOTE = (
    "Note: you already made this exact call in this request and got the same result; use it and move on "
    "to the next step instead of repeating it.\n"
)
REPLAYED_NOTE = "This call id already ran in this request and was not run again. Previous result:\n"


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


def cap_result(result: ToolResult) -> ToolResult:
    if len(result.content) <= MAX_TOOL_RESULT_CHARS:
        return result
    note = RESULT_TRUNCATED.format(limit=MAX_TOOL_RESULT_CHARS)
    return ToolResult(result.tool_call_id, result.name, result.content[:MAX_TOOL_RESULT_CHARS] + note)


def run_registered(registry: NativeToolRegistry, call: ToolCall) -> tuple[ToolResult, bool]:
    """Run one call; any failure becomes an error result the model can read. Returns (result, failed)."""
    try:
        return registry.execute(call), False
    except Exception as err:  # tool handlers may raise anything; the model gets the message
        return ToolResult(tool_call_id=call.id, name=call.name, content=f"{TOOL_ERROR_PREFIX}{err}"), True


def execute_tool_call(
    registry: NativeToolRegistry, call: ToolCall, ledger: Optional[OperationLedger] = None
) -> ToolResult:
    """Run one call and record it in `ledger` (None: no record); a call id that already ran is not rerun."""
    if ledger is None:
        return cap_result(run_registered(registry, call)[0])
    previous = ledger.finished(call.id)
    if previous is not None:
        return ToolResult(call.id, call.name, REPLAYED_NOTE + previous.result)
    record = ledger.begin(call.id, call.name, call.arguments)
    try:
        result, failed = run_registered(registry, call)
    except KeyboardInterrupt:
        # Close the record so the ledger never shows an interrupted call as still running or approved.
        ledger.finish(record, INTERRUPTED_RESULT, failed=True)
        raise
    result = cap_result(result)
    ledger.finish(record, result.content, failed)
    if call.name in REPEAT_HINT_TOOLS and ledger.ran_before(record):
        # Local models can loop on re-reading; say plainly that this exact result is already in the conversation.
        return ToolResult(result.tool_call_id, result.name, REPEAT_NOTE + result.content)
    return result


def build_tool_round_messages(
    registry: NativeToolRegistry,
    content: str,
    calls: list[ToolCall],
    ledger: Optional[OperationLedger] = None,
) -> list[dict[str, Any]]:
    """Messages to append after a tool-calling turn: the turn itself, then each result."""
    results = [execute_tool_call(registry, call, ledger) for call in calls]
    return [assistant_tool_call_message(content, calls)] + [
        make_tool_result_message(result) for result in results
    ]


def answered_ids(messages: list[dict[str, Any]], start: int) -> set[str]:
    """tool_call_ids of the tool messages directly after index `start`."""
    ids = set()
    for message in messages[start + 1 :]:
        if message.get("role") != "tool":
            break
        ids.add(message.get("tool_call_id"))
    return ids


def drop_orphan_tool_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Make history valid for strict servers after truncation, summaries or interruptions.

    Tool messages must answer a tool call of the assistant message right before them, and every kept tool call
    must have an answer; unanswered calls are removed from their assistant message.
    """
    cleaned: list[dict[str, Any]] = []
    open_ids: set[str] = set()
    for index, message in enumerate(messages):
        if message.get("role") == "tool":
            if message.get("tool_call_id") in open_ids:
                cleaned.append(message)
            continue
        open_ids = set()
        if message.get("role") == "assistant" and message.get("tool_calls"):
            answered = answered_ids(messages, index)
            calls = [c for c in message["tool_calls"] if c.get("id") in answered]
            open_ids = {c["id"] for c in calls}
            message = {k: v for k, v in message.items() if k != "tool_calls"}
            if calls:
                message["tool_calls"] = calls
        cleaned.append(message)
    return cleaned
