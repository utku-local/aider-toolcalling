"""Drives the native tool-calling loop for a Coder after a non-streaming completion.
While the model replies with tool calls, it executes them, appends the tool messages and queries the model again.
After MAX_TOOL_ROUNDS it asks once more with tool_choice "none" so the turn still ends with an answer.
"""

from typing import Any, Optional

from aider.native_tool_calls import describe_call, normalize_tool_calls, visible_content
from aider.native_tool_loop import (
    FINAL_ANSWER_CHOICE,
    MAX_TOOL_ROUNDS,
    build_tool_round_messages,
)

NO_STREAM = False


def first_message(completion: Any) -> Optional[Any]:
    choices = getattr(completion, "choices", None)
    return choices[0].message if choices else None


def request(
    coder: Any,
    model: Any,
    messages: list[dict[str, Any]],
    functions: Optional[list[dict[str, Any]]],
    tool_choice: Optional[str],
) -> Any:
    hash_object, completion = model.send_completion(
        messages,
        functions,
        NO_STREAM,
        coder.temperature,
        tools=coder.native_tools.schemas(),
        tool_choice=tool_choice,
    )
    coder.chat_completion_call_hashes.append(hash_object.hexdigest())
    coder.show_send_output(completion)
    return completion


def run_tool_round(
    coder: Any, messages: list[dict[str, Any]], completion: Any, round_index: int
) -> bool:
    """Execute the tool calls of `completion`; False when it requested none."""
    message = first_message(completion)
    calls = normalize_tool_calls(message, round_index)
    if not calls:
        return False

    # Native tool calls are not legacy edit-format function calls.
    coder.partial_response_function_call = dict()
    for call in calls:
        coder.io.tool_output(f"Running tool: {describe_call(call)}")
    round_messages = build_tool_round_messages(coder.native_tools, visible_content(message), calls)
    messages.extend(round_messages)
    # Keep the exchange in the chat history so later turns remember what the tools returned.
    coder.cur_messages += round_messages
    coder.calculate_and_show_tokens_and_cost(messages, completion)
    return True


def run_native_tool_rounds(
    coder: Any,
    model: Any,
    messages: list[dict[str, Any]],
    functions: Optional[list[dict[str, Any]]],
    completion: Any,
) -> Any:
    """Execute requested tools and re-query the model until it answers without tools."""
    for round_index in range(MAX_TOOL_ROUNDS):
        if not run_tool_round(coder, messages, completion, round_index):
            return completion
        completion = request(coder, model, messages, functions, None)

    if run_tool_round(coder, messages, completion, MAX_TOOL_ROUNDS):
        coder.io.tool_warning(
            f"Reached {MAX_TOOL_ROUNDS} tool rounds; asking the model to answer without tools."
        )
        completion = request(coder, model, messages, functions, FINAL_ANSWER_CHOICE)
        coder.partial_response_function_call = dict()
        coder.partial_response_content = visible_content(first_message(completion))
    return completion
