"""Drives the native tool-calling loop for a Coder, streamed or not.
While the model replies with tool calls, it executes them through the operation ledger, appends the tool messages
to the caller's message list (so an API retry resumes after the rounds already done) and queries the model again.
Each request is sent with old tool results compacted and the ledger's working state attached; at the round budget
the user may extend it, otherwise the model is asked once more with tool_choice "none" and a user message to answer.
A round with a repeated call gets a user message that pushes the model to the next step, and messages the user
typed at a prompt during the round follow as a user message of their own.
"""

import time
from typing import Any, Generator, Optional

from aider.native_tool_calls import describe_call, normalize_tool_calls, visible_content
from aider.native_tool_compaction import add_working_state, compact_tool_history
from aider.native_tool_loop import (
    FINAL_ANSWER_CHOICE,
    FINAL_ANSWER_NUDGE,
    REPEAT_NUDGE,
    REPEAT_REFUSAL_MARKER,
    build_tool_round_messages,
    drop_orphan_tool_messages,
    repeated_in_round,
)
from aider.native_loop_options import LoopOptions
from aider.native_task_gates import completion_nudge
from aider.native_tool_stream import ToolCallAccumulator
from aider.native_tool_summary import summarize_result
from aider.native_tools_websearch import NOT_SET_UP
from aider.native_working_state import render_working_state

from .native_context import maybe_summarize
from .native_tool_log import append_operation_log
from .native_tool_setup import read_unchanged
from .native_user_io import take_user_notes

MAX_CONTINUATIONS = 3
# After this many refused repeats in one request the loop stops and the model must answer.
MAX_REPEAT_REFUSALS = 3
RESULT_INDENT = "  -> "
BACKGROUND_HEADING = "## Background update\n"
# Tool results meant for the user, shown in full instead of as a one-line summary.
USER_NOTICES = frozenset({NOT_SET_UP})


def prepare_request_messages(coder: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What is actually sent: the working state added to the live list when it changed, then a copy with valid
    tool pairs and compacted old results. Each request extends the previous one, which keeps prefix caches warm."""
    if not coder.native_tools:
        return messages
    maybe_summarize(coder, messages)
    add_background_notices(coder, messages)
    tasks = coder.native_todos.render() if coder.native_todos.open_items() else ""
    add_working_state(messages, render_working_state(coder.native_ledger.records, tasks))
    return compact_tool_history(drop_orphan_tool_messages(messages))


def add_background_notices(coder: Any, messages: list[dict[str, Any]]) -> None:
    """Tell the model, once, about background processes that exited on their own."""
    processes = getattr(coder, "native_processes", None)
    notices = processes.exit_notices() if processes is not None else []
    if notices:
        messages.append({"role": "user", "content": BACKGROUND_HEADING + "\n".join(notices)})


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
        prepare_request_messages(coder, messages),
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


def show_results(coder: Any, round_messages: list[dict[str, Any]]) -> None:
    for message in round_messages[1:]:
        content = message["content"]
        coder.io.tool_output(RESULT_INDENT + summarize_result(message["name"], content))
        if content in USER_NOTICES:
            # Measured: told to pass this setup message on, a local model went on without mentioning it.
            coder.io.tool_warning(content)
        elif coder.verbose:
            coder.io.tool_output(content)


def run_tool_round(coder: Any, messages: list[dict[str, Any]], completion: Any) -> int:
    """Execute the tool calls of the last reply; returns how many there were."""
    message = current_message(coder, completion)
    coder.native_round_serial += 1
    calls = normalize_tool_calls(message, coder.native_round_serial)
    if not calls:
        return 0

    start_new_display(coder)
    # Native tool calls are not legacy edit-format function calls.
    coder.partial_response_function_call = dict()
    for call in calls:
        coder.io.tool_output(f"Running tool: {describe_call(call)}")
    logged = len(coder.native_ledger.records)
    round_messages = build_tool_round_messages(
        coder.native_tools, visible_content(message), calls, coder.native_ledger,
        LoopOptions(has_plan=lambda: bool(coder.native_todos.items), spill=getattr(coder, "native_spill", None),
                    hooks=getattr(coder, "native_hooks", None),
                    file_unchanged=lambda arguments: read_unchanged(coder, arguments)),
    )
    show_results(coder, round_messages)
    append_operation_log(coder, coder.native_ledger.records[logged:])
    if repeated_in_round(round_messages):
        round_messages.append({"role": "user", "content": REPEAT_NUDGE})
    note = take_user_notes(coder)
    if note is not None:
        round_messages.append(note)
    messages.extend(round_messages)
    # Keep the exchange in the chat history so later turns remember what the tools returned.
    coder.cur_messages += round_messages
    coder.calculate_and_show_tokens_and_cost(messages, None if coder.stream else completion)
    return len(calls)


def finish_nudge(coder: Any) -> str:
    """The once-per-request reminder to verify or finish open tasks; empty when the answer may stand."""
    ledger = coder.native_ledger
    if getattr(coder, "native_nudged_request", None) == ledger.request:
        return ""
    open_tasks = coder.native_todos.render() if coder.native_todos.open_items() else ""
    nudge = completion_nudge(ledger, open_tasks)
    if nudge:
        coder.native_nudged_request = ledger.request
    return nudge


def send_back(coder: Any, messages: list[dict[str, Any]], completion: Any, nudge: str) -> None:
    """Keep the model's answer in the conversation and ask it to close the gaps before finishing."""
    start_new_display(coder)
    coder.io.tool_output(f"Sending the answer back: {nudge.splitlines()[1]}")
    exchange = [
        {"role": "assistant", "content": visible_content(current_message(coder, completion))},
        {"role": "user", "content": nudge},
    ]
    messages.extend(exchange)
    coder.cur_messages += exchange


def report(coder: Any, rounds: int, calls: int, started: float) -> None:
    if rounds:
        if coder.stream and not coder.mdstream:
            # plain streamed text ends without a newline; keep the summary on its own line
            coder.io.tool_output()
        elapsed = time.monotonic() - started
        coder.io.tool_output(f"Native tools: {rounds} round(s), {calls} call(s), {elapsed:.1f}s")


def may_continue(coder: Any, rounds: int, continuations: int) -> bool:
    if continuations >= MAX_CONTINUATIONS:
        return False
    return coder.io.confirm_ask(
        f"The model used {rounds} tool rounds. Allow {coder.max_tool_rounds} more?"
    )


def run_native_tool_rounds(
    coder: Any,
    model: Any,
    messages: list[dict[str, Any]],
    functions: Optional[list[dict[str, Any]]],
    completion: Any,
) -> Generator[str, None, Any]:
    """Execute requested tools and re-query the model until it answers without tools."""
    started = time.monotonic()
    rounds = calls = continuations = 0
    budget = coder.max_tool_rounds
    while True:
        executed = run_tool_round(coder, messages, completion)
        if not executed:
            nudge = finish_nudge(coder)
            if not nudge:
                report(coder, rounds, calls, started)
                return completion
            send_back(coder, messages, completion, nudge)
        rounds, calls = rounds + 1, calls + executed
        if coder.native_ledger.repeat_refusals(REPEAT_REFUSAL_MARKER) >= MAX_REPEAT_REFUSALS:
            coder.io.tool_warning("The model keeps repeating identical tool calls; asking it to answer now.")
            break
        if rounds >= budget:
            if not may_continue(coder, rounds, continuations):
                break
            continuations, budget = continuations + 1, budget + coder.max_tool_rounds
        completion = yield from request(coder, model, messages, functions, None)

    coder.io.tool_warning(f"Stopped after {rounds} tool rounds; asking the model to answer without tools.")
    messages.append({"role": "user", "content": FINAL_ANSWER_NUDGE})
    completion = yield from request(coder, model, messages, functions, FINAL_ANSWER_CHOICE)
    coder.partial_response_function_call = dict()
    coder.partial_response_content = visible_content(current_message(coder, completion))
    report(coder, rounds, calls, started)
    return completion
