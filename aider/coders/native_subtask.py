"""The research tool: answers a question in a separate, small conversation that only uses read-only tools.
The sub-conversation starts from just the question, runs its own tool loop on the same model, and returns only its
final answer, so file contents it reads never enter the main conversation's prompt.
It is capped at SUBTASK_MAX_ROUNDS rounds, after which the model must answer with what it has.
"""

from typing import Any, Optional

from aider.native_tool_calls import describe_call, normalize_tool_calls, visible_content
from aider.native_tool_loop import FINAL_ANSWER_CHOICE, build_tool_round_messages
from aider.native_toolcalling import NativeToolRegistry

SUBTASK_MAX_ROUNDS = 10
NO_STREAM = False
NO_FUNCTIONS = None
SUBTASK_PREFIX = "  research: "
EMPTY_ANSWER = "The research step found no answer."
SUBTASK_SYSTEM = """You are a research assistant inside a coding agent. Answer the question about the user's project
using your read-only tools (search_code, find_symbol, find_files, list_files, read_file, git). Read only what you
need, and prefer line ranges for large files. Reply with a short, factual answer: file paths with line numbers and
the facts that answer the question. Do not propose or make changes."""

RESEARCH_PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "A self-contained question about the project, e.g. where something is defined or how "
            "a component works.",
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


def run_subtask(coder: Any, registry: NativeToolRegistry, question: str) -> str:
    """Answer `question` in a fresh conversation with `registry`'s tools; returns only the final answer."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SUBTASK_SYSTEM},
        {"role": "user", "content": question},
    ]
    for round_index in range(SUBTASK_MAX_ROUNDS + 1):
        final = round_index == SUBTASK_MAX_ROUNDS
        message = ask_model(coder, registry, messages, FINAL_ANSWER_CHOICE if final else None)
        coder.native_round_serial += 1
        calls = [] if final else normalize_tool_calls(message, coder.native_round_serial)
        if not calls:
            return visible_content(message) or EMPTY_ANSWER
        for call in calls:
            coder.io.tool_output(SUBTASK_PREFIX + describe_call(call))
        messages.extend(build_tool_round_messages(registry, visible_content(message), calls, coder.native_ledger))
    return EMPTY_ANSWER


def register_research_tool(registry: NativeToolRegistry, coder: Any, read_registry: NativeToolRegistry) -> None:
    """Add research, which runs sub-conversations with `read_registry`'s tools, to `registry`."""
    registry.register(
        "research",
        "Answer a question about the project in a separate conversation with read-only tools and get back only "
        "the answer. Use it for exploration that would need many reads, to keep this conversation short.",
        RESEARCH_PARAMETERS,
        lambda question: run_subtask(coder, read_registry, question),
    )
