"""Drives the native tool-calling loop for a Coder after a non-streaming completion.
While the model replies with tool_calls, it executes them, appends the tool messages and queries the model again.
It stops when the model answers without tools or after MAX_TOOL_ROUNDS round trips, and returns the final completion.
"""

from typing import Any, Optional

from aider.native_tool_loop import (
    MAX_TOOL_ROUNDS,
    build_tool_round_messages,
    get_tool_calls,
    tool_call_name,
)

NO_STREAM = False


def first_message(completion: Any) -> Optional[Any]:
    choices = getattr(completion, "choices", None)
    return choices[0].message if choices else None


def run_native_tool_rounds(
    coder: Any,
    model: Any,
    messages: list[dict[str, Any]],
    functions: Optional[list[dict[str, Any]]],
    completion: Any,
) -> Any:
    """Execute requested tools and re-query the model until it answers without tools."""
    for _ in range(MAX_TOOL_ROUNDS):
        message = first_message(completion)
        tool_calls = get_tool_calls(message)
        if not tool_calls:
            return completion

        # Native tool calls are not legacy edit-format function calls.
        coder.partial_response_function_call = dict()
        for call in tool_calls:
            coder.io.tool_output(f"Running tool: {tool_call_name(call)}")
        messages.extend(build_tool_round_messages(coder.native_tools, message))
        coder.calculate_and_show_tokens_and_cost(messages, completion)

        hash_object, completion = model.send_completion(
            messages,
            functions,
            NO_STREAM,
            coder.temperature,
            tools=coder.native_tools.schemas(),
        )
        coder.chat_completion_call_hashes.append(hash_object.hexdigest())
        coder.show_send_output(completion)

    if get_tool_calls(first_message(completion)):
        coder.partial_response_function_call = dict()
        coder.io.tool_warning(f"Stopped after {MAX_TOOL_ROUNDS} tool rounds.")
    return completion
