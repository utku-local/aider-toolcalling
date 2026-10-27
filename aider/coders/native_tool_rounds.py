"""Drives the native tool-calling loop for a Coder, streamed or not.
While the model replies with tool calls, it executes them, appends the tool messages and queries the model again,
streaming each follow-up reply when the coder streams; streamed tool calls come from the coder's accumulator.
After MAX_TOOL_ROUNDS it asks once more with tool_choice "none", and it reports rounds, calls and elapsed time.
"""

import time
from typing import Any, Generator, Optional

from aider.native_tool_calls import describe_call, normalize_tool_calls, visible_content
from aider.native_tool_loop import (
    FINAL_ANSWER_CHOICE,
    MAX_TOOL_ROUNDS,
    build_tool_round_messages,
)
from aider.native_tool_stream import ToolCallAccumulator


def first_message(completion: Any) -> Optional[Any]:
    choices = getattr(completion, "choices", None)
    return choices[0].message if choices else None


def current_message(coder: Any, completion: Any) -> Optional[Any]:
    """The reply just shown: assembled from stream deltas, or the completion's message."""
    if coder.stream:
        return coder.native_stream_calls.message(coder.partial_response_content)
    return first_message(completion)


def start_new_display(coder: Any) -> None:
    """Close the live markdown view of the previous round before tool output is printed."""
    if coder.mdstream:
        coder.live_incremental_response(True)
        coder.mdstream = coder.io.get_assistant_mdstream()


def request(
    coder: Any,
    model: Any,
    messages: list[dict[str, Any]],
    functions: Optional[list[dict[str, Any]]],
    tool_choice: Optional[str],
) -> Generator[str, None, Any]:
    hash_object, completion = model.send_completion(
        messages,
        functions,
        coder.stream,
        coder.temperature,
        tools=coder.native_tools.schemas(),
        tool_choice=tool_choice,
    )
    coder.chat_completion_call_hashes.append(hash_object.hexdigest())
    if coder.stream:
        coder.partial_response_content = ""
        coder.native_stream_calls = ToolCallAccumulator()
        yield from coder.show_send_output_stream(completion)
    else:
        coder.show_send_output(completion)
    return completion


def run_tool_round(
    coder: Any, messages: list[dict[str, Any]], completion: Any, round_index: int
) -> int:
    """Execute the tool calls of the last reply; returns how many there were."""
    message = current_message(coder, completion)
    calls = normalize_tool_calls(message, round_index)
    if not calls:
        return 0

    start_new_display(coder)
    # Native tool calls are not legacy edit-format function calls.
    coder.partial_response_function_call = dict()
    for call in calls:
        coder.io.tool_output(f"Running tool: {describe_call(call)}")
    round_messages = build_tool_round_messages(coder.native_tools, visible_content(message), calls)
    messages.extend(round_messages)
    # Keep the exchange in the chat history so later turns remember what the tools returned.
    coder.cur_messages += round_messages
    coder.calculate_and_show_tokens_and_cost(messages, None if coder.stream else completion)
    return len(calls)


def report(coder: Any, rounds: int, calls: int, started: float) -> None:
    if rounds:
        elapsed = time.monotonic() - started
        coder.io.tool_output(f"Native tools: {rounds} round(s), {calls} call(s), {elapsed:.1f}s")


def run_native_tool_rounds(
    coder: Any,
    model: Any,
    messages: list[dict[str, Any]],
    functions: Optional[list[dict[str, Any]]],
    completion: Any,
) -> Generator[str, None, Any]:
    """Execute requested tools and re-query the model until it answers without tools."""
    started = time.monotonic()
    rounds = calls = 0
    for round_index in range(MAX_TOOL_ROUNDS):
        executed = run_tool_round(coder, messages, completion, round_index)
        if not executed:
            report(coder, rounds, calls, started)
            return completion
        rounds, calls = rounds + 1, calls + executed
        completion = yield from request(coder, model, messages, functions, None)

    executed = run_tool_round(coder, messages, completion, MAX_TOOL_ROUNDS)
    if executed:
        rounds, calls = rounds + 1, calls + executed
        coder.io.tool_warning(
            f"Reached {MAX_TOOL_ROUNDS} tool rounds; asking the model to answer without tools."
        )
        completion = yield from request(coder, model, messages, functions, FINAL_ANSWER_CHOICE)
        coder.partial_response_function_call = dict()
        coder.partial_response_content = visible_content(current_message(coder, completion))
    report(coder, rounds, calls, started)
    return completion
