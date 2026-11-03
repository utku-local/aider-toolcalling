"""Sub-conversations: research answers a question with read-only tools, task carries out a delegated job with all tools.
Each starts from just its brief, runs its own tool loop on the same model and returns only its final answer, so the
files it reads never enter the main conversation's prompt; task's edits and commands still need the usual approvals.
Each is capped in rounds (research 10, task 30), after which the model must answer with what it has; it must also
answer once three of its calls were refused as repeats, as the main loop does.
"""

from typing import Any, Optional

from aider.native_loop_options import NO_OPTIONS, LoopOptions
from aider.native_tool_calls import describe_call, normalize_tool_calls, visible_content
from aider.native_tool_loop import FINAL_ANSWER_CHOICE, REPEAT_REFUSAL_MARKER, build_tool_round_messages
from aider.native_toolcalling import NativeToolRegistry

SUBTASK_MAX_ROUNDS = 10
TASK_MAX_ROUNDS = 30
# Refused repeats (an identical call, or one the user declined) after which the sub-conversation must answer.
# Measured: a task sub-agent re-sent a declined fetch_url 8 times in a row and only the round cap would end it.
SUBTASK_MAX_REPEAT_REFUSALS = 3
REPEAT_STOP_WARNING = "The sub-agent keeps repeating refused tool calls; asking it to answer now."
NO_STREAM = False
NO_FUNCTIONS = None
SUBTASK_PREFIX = "  research: "
TASK_PREFIX = "  task: "
EMPTY_ANSWER = "The research step found no answer."
SUBTASK_SYSTEM = """You are a research assistant inside a coding agent. Answer the question about the user's project
using your read-only tools (search_code, find_symbol, find_files, list_files, read_file, git). Read only what you
need, and prefer line ranges for large files. Reply with a short, factual answer: file paths with line numbers and
the facts that answer the question. Do not propose or make changes."""

TASK_SYSTEM = """You are a sub-agent inside a coding agent, given one self-contained job in the user's project.
Do it with your tools: read what you need, make the changes, and verify them (run the tests or a command that
exercises the change). Your edits and commands are checked and approved like the main agent's. Reply with a short
report: what you changed (files and why), how you verified it, and anything left undone. Do not ask questions."""
TASK_PARAMETERS = {
    "type": "object",
    "properties": {
        "brief": {
            "type": "string",
            "description": "The goal, the files involved, and how to verify it.",
        },
    },
    "required": ["brief"],
}

RESEARCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "Self-contained, e.g. where something is defined or how a component works.",
        },
    },
    "required": ["question"],
}


def first_message(completion: Any) -> Optional[Any]:
    choices = getattr(completion, "choices", None)
    return choices[0].message if choices else None


def ask_model(coder: Any, registry: NativeToolRegistry, messages: list[dict[str, Any]], choice: Any) -> Any:
    _, completion = coder.main_model.send_completion(
        messages, NO_FUNCTIONS, NO_STREAM, coder.temperature, tools=registry.schemas(), tool_choice=choice
    )
    return first_message(completion)


def run_subtask(
    coder: Any, registry: NativeToolRegistry, question: str, system: str = SUBTASK_SYSTEM,
    max_rounds: int = SUBTASK_MAX_ROUNDS, prefix: str = SUBTASK_PREFIX, options: LoopOptions = NO_OPTIONS,
) -> str:
    """Answer `question` in a fresh conversation with `registry`'s tools; returns only the final answer.

    Defaults are research's: its system prompt, round cap and output prefix, with no loop options."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]
    refusals_before = coder.native_ledger.repeat_refusals(REPEAT_REFUSAL_MARKER)
    repeating = False
    for round_index in range(max_rounds + 1):
        final = round_index == max_rounds or repeating
        message = ask_model(coder, registry, messages, FINAL_ANSWER_CHOICE if final else None)
        coder.native_round_serial += 1
        calls = [] if final else normalize_tool_calls(message, coder.native_round_serial)
        if not calls:
            return visible_content(message) or EMPTY_ANSWER
        for call in calls:
            coder.io.tool_output(prefix + describe_call(call))
        messages.extend(
            build_tool_round_messages(registry, visible_content(message), calls, coder.native_ledger, options)
        )
        refused = coder.native_ledger.repeat_refusals(REPEAT_REFUSAL_MARKER) - refusals_before
        if refused >= SUBTASK_MAX_REPEAT_REFUSALS:
            coder.io.tool_warning(REPEAT_STOP_WARNING)
            repeating = True
    return EMPTY_ANSWER


def register_research_tool(registry: NativeToolRegistry, coder: Any, read_registry: NativeToolRegistry) -> None:
    """Add research, which runs sub-conversations with `read_registry`'s tools, to `registry`."""
    registry.register(
        "research",
        "Answer a project question in a separate read-only conversation; only the answer comes back.",
        RESEARCH_PARAMETERS,
        lambda question: run_subtask(coder, read_registry, question),
    )


def register_task_tool(registry: NativeToolRegistry, coder: Any, task_registry: NativeToolRegistry,
                       options: LoopOptions) -> None:
    """Add task, which runs a delegated job in a sub-conversation with `task_registry`'s tools."""
    registry.register(
        "task",
        "Delegate a self-contained job (e.g. update every caller of a renamed function and run the tests) to a "
        "sub-agent with your tools; only its report comes back.",
        TASK_PARAMETERS,
        lambda brief: run_subtask(coder, task_registry, brief, TASK_SYSTEM, TASK_MAX_ROUNDS, TASK_PREFIX, options),
    )
