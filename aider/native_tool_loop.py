"""Pure helpers for one round of the native tool-calling loop.
Given normalized ToolCalls, they build the assistant tool_calls message and one tool result message per call,
executing each call through a NativeToolRegistry.
Tool failures are reported back to the model as tool results instead of interrupting the conversation.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Optional

from aider.native_tool_calls import ToolCall, field
from aider.native_sensitive import is_sensitive
from aider.native_tool_ledger import CHANGE_TOOLS, OperationLedger
from aider.native_hooks import after_notes, blocked_by
from aider.native_loop_options import NO_OPTIONS, LoopOptions
from aider.native_output_spill import OutputSpill
from aider.native_task_gates import PLAN_FIRST, needs_plan
from aider.native_tool_compaction import is_state_message
from aider.native_tool_summary import REPEAT_NOTE, exit_code
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
PARALLEL_TOOLS = frozenset(
    {"read_file", "list_files", "find_files", "search_code", "find_symbol", "git", "read_spreadsheet"}
)
READ_FILE_TOOL = "read_file"
MAX_PARALLEL_CALLS = 8
REPEAT_HINT_TOOLS = frozenset({"read_file", "list_files", "find_files", "search_code", "find_symbol", "git"})
# Measured: a local model ran the same passing test command 100 times without changing a file in between.
# Measured: Qwen3-Coder-Next sent the same todo_write 98 times in one request.
REPEAT_GUARD_TOOLS = REPEAT_HINT_TOOLS | {"run_command", "todo_write"}
REPEAT_REFUSE_AFTER = 2
REPEAT_REFUSAL = (
    "Error: refused, this exact call already ran {count} times in this request and its result is unchanged "
    "in the conversation above and no file changed since. Do not repeat it: edit the code, or give your answer."
)
REPEAT_REFUSAL_MARKER = "Error: refused, this exact call already ran"
# Measured: a local model kept searching for functions it had not written yet; the refusal and note in the tool
# result did not stop it, a user message did (it wrote its plan next).
REPEAT_NUDGE = (
    "You are repeating a call whose result has not changed, so repeating it again will not change it. If it found "
    "nothing because the code does not exist yet, that is the answer. Take the next step of the task now "
    "(write the plan with todo_write, or make the change)."
)
# Measured: the repeat stop ended a long task before the model ran its tests, which then failed; one more chance
# with this message lets it go on with the remaining steps.
REPEAT_STOP_NUDGE = (
    "Several of your repeated calls were refused. Stop looking for that: if a search found nothing, it does not "
    "exist. Go on with the remaining steps of the task (the open tasks in the working state), and run the tests "
    "after changing code. If you cannot go further, give your answer."
)
# Measured: asked to answer with tool_choice "none", a local model still wrote a tool call, which left the answer
# empty; an explicit user message got a plain-text summary.
FINAL_ANSWER_NUDGE = (
    "Stop using tools now. Answer the user in plain text: what you found, what you changed (if anything), and what "
    "is left to do. Do not write a tool call."
)
# Measured: a local model sent one edit 70 times; its new_string contained old_string, so every call succeeded
# and added the same line again. Applying an identical edit twice is never what the model meant.
REPEAT_EDIT_REFUSAL = (
    REPEAT_REFUSAL_MARKER + " and this edit is already applied. Read the file to see its current content "
    "before changing it again."
)
# Measured: a local model re-read two unchanged files and ran `pip list | grep` twice in a row; the guard above
# only stopped the third run. A re-read of an unchanged file and a command repeated back to back are refused at once.
REPEAT_READ_REFUSAL = (
    REPEAT_REFUSAL_MARKER + " in this request and the file has not changed since, so its content above is current. "
    "Use it; if it is no longer shown in full, read only the lines you need with start_line and end_line."
)
REPEAT_COMMAND_REFUSAL = (
    REPEAT_REFUSAL_MARKER + " as the call right before this one, so its result above still holds. Use it: run a "
    "different command, change the code, or give your answer."
)
# Measured: a local model sent the same declined command more than 30 times; declined calls were never counted.
REPEAT_DENIED_REFUSAL = (
    REPEAT_REFUSAL_MARKER + " and the user declined it. Do not ask again: use another approach, or stop and ask "
    "the user how to proceed."
)
COMMAND_TOOL = "run_command"
HasPlan = Callable[[], bool]
# Measured: a local model spent half an hour retrying connections that the sandbox and a stopped service refused.
FAILING_STREAK_LIMIT = 4
FAILING_STREAK_NOTE = (
    "\nNote: the last {count} commands all failed. Stop retrying: summarize what you tried and what blocks you, "
    "and ask the user how to proceed."
)
REPLAYED_NOTE = "This call id already ran in this request and was not run again. Previous result:\n"


def repeat_refusal(ledger: OperationLedger, call: ToolCall, has_plan: Optional[HasPlan] = None) -> str:
    """Refusal for a call the user already declined, an edit already applied, or a change made before a plan
    (`has_plan` None: no plan check); empty to let it run."""
    if has_plan is not None and needs_plan(ledger, call.name, has_plan()):
        return PLAN_FIRST
    if ledger.denied_before(call.name, call.arguments):
        return REPEAT_DENIED_REFUSAL
    if call.name in CHANGE_TOOLS and ledger.applied_before(call.name, call.arguments):
        return REPEAT_EDIT_REFUSAL
    return ""


def early_repeat_refusal(call: ToolCall, repeats: int, back_to_back: bool, options: LoopOptions) -> str:
    """Refusal for the first repeat of a read whose file is unchanged, or of the command run just before; empty
    otherwise. `repeats` counts earlier runs since the last change, `back_to_back` says the previous call matched."""
    if not repeats:
        return ""
    if call.name == READ_FILE_TOOL and options.file_unchanged is not None and options.file_unchanged(call.arguments):
        return REPEAT_READ_REFUSAL
    if call.name == COMMAND_TOOL and back_to_back:
        return REPEAT_COMMAND_REFUSAL
    return ""


def failing_command_streak(ledger: OperationLedger) -> int:
    """Commands that failed in a row (non-zero exit) in the current request, counting back from the latest one."""
    streak = 0
    for record in reversed(ledger.executed()):
        if record.request != ledger.request:
            break
        if record.tool != COMMAND_TOOL:
            continue
        if not exit_code(record.result):
            break
        streak += 1
    return streak


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


def cap_result(result: ToolResult, spill: Optional[OutputSpill] = None) -> ToolResult:
    """A result within the limit; a longer one is saved whole to a file (`spill`) or truncated."""
    if len(result.content) <= MAX_TOOL_RESULT_CHARS:
        return result
    if spill is not None:
        return ToolResult(result.tool_call_id, result.name, spill.shorten(result.content, result.name))
    note = RESULT_TRUNCATED.format(limit=MAX_TOOL_RESULT_CHARS)
    return ToolResult(result.tool_call_id, result.name, result.content[:MAX_TOOL_RESULT_CHARS] + note)


def run_registered(registry: NativeToolRegistry, call: ToolCall) -> tuple[ToolResult, bool]:
    """Run one call; any failure becomes an error result the model can read. Returns (result, failed)."""
    try:
        return registry.execute(call), False
    except Exception as err:  # tool handlers may raise anything; the model gets the message
        return ToolResult(tool_call_id=call.id, name=call.name, content=f"{TOOL_ERROR_PREFIX}{err}"), True


def execute_tool_call(
    registry: NativeToolRegistry,
    call: ToolCall,
    ledger: Optional[OperationLedger] = None,
    options: LoopOptions = NO_OPTIONS,
) -> ToolResult:
    """Run one call and record it in `ledger` (None: no record); a call id that already ran is not rerun."""
    if ledger is None:
        return cap_result(run_registered(registry, call)[0], options.spill)
    previous = ledger.finished(call.id)
    if previous is not None:
        return ToolResult(call.id, call.name, REPLAYED_NOTE + previous.result)
    repeats = ledger.times_run(call.name, call.arguments) if call.name in REPEAT_GUARD_TOOLS else 0
    back_to_back = ledger.repeats_last(call.name, call.arguments)
    refusal = repeat_refusal(ledger, call, options.has_plan)
    if not refusal and options.hooks is not None:
        refusal = blocked_by(options.hooks, call.name, call.arguments)
    record = ledger.begin(call.id, call.name, call.arguments)
    if refusal:
        ledger.finish(record, refusal, failed=True)
        return ToolResult(call.id, call.name, refusal)
    refusal = early_repeat_refusal(call, repeats, back_to_back, options)
    if not refusal and repeats >= REPEAT_REFUSE_AFTER:
        # Measured: a local model re-read one file range 66 times despite the note; stop feeding the loop.
        refusal = REPEAT_REFUSAL.format(count=repeats)
    if refusal:
        ledger.finish(record, refusal, failed=True)
        return ToolResult(call.id, call.name, refusal)
    try:
        result, failed = run_registered(registry, call)
    except KeyboardInterrupt:
        # Close the record so the ledger never shows an interrupted call as still running or approved.
        ledger.finish(record, INTERRUPTED_RESULT, failed=True)
        raise
    result = cap_result(result, options.spill)
    if options.hooks is not None:
        notes = after_notes(options.hooks, call.name, call.arguments, result.content)
        result = ToolResult(result.tool_call_id, result.name, result.content + notes) if notes else result
    ledger.finish(record, result.content, failed)
    streak = failing_command_streak(ledger) if call.name == COMMAND_TOOL else 0
    if streak >= FAILING_STREAK_LIMIT:
        result = ToolResult(result.tool_call_id, result.name, result.content + FAILING_STREAK_NOTE.format(count=streak))
    if call.name in REPEAT_HINT_TOOLS and repeats:
        # Local models can loop on re-reading; say plainly that this exact result is already in the conversation.
        return ToolResult(result.tool_call_id, result.name, REPEAT_NOTE + result.content)
    return result


def repeated_in_round(round_messages: list[dict[str, Any]]) -> bool:
    """Whether any tool result of a round says the call repeated an earlier one."""
    return any(
        message.get("role") == "tool"
        and str(message.get("content", "")).startswith((REPEAT_NOTE, REPEAT_REFUSAL_MARKER))
        for message in round_messages
    )


def runs_in_parallel(call: ToolCall) -> bool:
    """Read-only tools that never prompt; read_file only for paths that are not secret files."""
    if call.name not in PARALLEL_TOOLS:
        return False
    if call.name != READ_FILE_TOOL:
        return True
    try:
        path = json.loads(call.arguments).get("path")
    except (ValueError, AttributeError):
        return False
    return isinstance(path, str) and not is_sensitive(path)


def build_tool_round_messages(
    registry: NativeToolRegistry,
    content: str,
    calls: list[ToolCall],
    ledger: Optional[OperationLedger] = None,
    options: LoopOptions = NO_OPTIONS,
) -> list[dict[str, Any]]:
    """Messages to append after a tool-calling turn: the turn itself, then each result in call order.

    Read-only calls that can never ask the user run concurrently; everything else runs one by one, in order.
    """
    results: dict[int, ToolResult] = {}
    parallel = [i for i, call in enumerate(calls) if runs_in_parallel(call)]
    if len(parallel) > 1:
        with ThreadPoolExecutor(max_workers=min(len(parallel), MAX_PARALLEL_CALLS)) as pool:
            read_only = LoopOptions(spill=options.spill, hooks=options.hooks, file_unchanged=options.file_unchanged)
            futures = {i: pool.submit(execute_tool_call, registry, calls[i], ledger, read_only) for i in parallel}
            results = {i: future.result() for i, future in futures.items()}
    for i, call in enumerate(calls):
        if i not in results:
            results[i] = execute_tool_call(registry, call, ledger, options)
    return [assistant_tool_call_message(content, calls)] + [
        make_tool_result_message(results[i]) for i in range(len(calls))
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


def drop_refused_repeats(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The request without refused repeat calls, their refusals and repeated user messages between two replies.

    Measured: once the context held several identical call/refusal pairs, a local model kept making the same call
    whatever it was told; with the pairs removed it went on with the task.
    """
    refused = {
        message.get("tool_call_id")
        for message in messages
        if message.get("role") == "tool" and str(message.get("content", "")).startswith(REPEAT_REFUSAL_MARKER)
    }
    kept: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role")
        if role == "tool" and message.get("tool_call_id") in refused:
            continue
        if role == "assistant" and message.get("tool_calls"):
            calls = [call for call in message["tool_calls"] if call.get("id") not in refused]
            if not calls and not message.get("content"):
                continue
            message = {**message, "tool_calls": calls} if calls else {
                k: v for k, v in message.items() if k != "tool_calls"}
        if role == "user":
            drop_earlier_copy(kept, message)
        kept.append(message)
    return kept


def drop_earlier_copy(kept: list[dict[str, Any]], message: dict[str, Any]) -> None:
    """Remove an older copy of `message` (same text, or an older working state) from the user messages that end
    `kept`; two copies only meet there once refused repeats between them were removed."""
    index = len(kept) - 1
    while index >= 0 and kept[index].get("role") == "user":
        older = kept[index]
        if older.get("content") == message.get("content") or (is_state_message(older) and is_state_message(message)):
            del kept[index]
            return
        index -= 1
