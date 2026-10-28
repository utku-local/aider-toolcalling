"""Shrinks tool history before each request and attaches the working state, without changing the stored history.
Nothing is changed until the history passes a large trigger, so a server with a prefix cache reuses every earlier
round; past it, the history is brought down to a target in one step: superseded file reads first, then command,
search and edit results, file contents last, because a model that loses a file it still needs reads it again.
Every function returns new lists and dicts, so the full history stays available for later turns and for review.
"""

import json
from typing import Any

from aider.native_tool_summary import summarize_result
from aider.native_working_state import STATE_HEADING

KEEP_FULL_ROUNDS = 2
# About 4 characters per token: compaction starts past ~48K tokens and brings the history to ~24K. With mlx_lm's
# prefix cache an unchanged history costs seconds per round; measured, compacting earlier made every round re-read
# the whole prompt (about 3 minutes at 66 tok/s), and losing file contents made the agent re-read files in a loop.
COMPACT_TRIGGER_CHARS = 192_000
COMPACT_TARGET_CHARS = 96_000
COMPACTED_PREFIX = "[compacted] "
STATE_ROLE = "user"
READ_TOOL = "read_file"
READ_KEY_FIELDS = ("path", "start_line", "end_line")


def round_starts(messages: list[dict[str, Any]]) -> list[int]:
    """Indexes of assistant messages that requested tools; each starts one tool round."""
    return [
        i for i, m in enumerate(messages) if m.get("role") == "assistant" and m.get("tool_calls")
    ]


def history_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(m.get("content") or "") for m in messages if isinstance(m.get("content"), str))


def call_arguments(messages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """tool_call_id -> decoded arguments, from the assistant tool_calls in `messages`."""
    found: dict[str, dict[str, Any]] = {}
    for message in messages:
        for call in message.get("tool_calls") or []:
            try:
                arguments = json.loads(call.get("function", {}).get("arguments") or "{}")
            except ValueError:
                arguments = {}
            found[call.get("id")] = arguments if isinstance(arguments, dict) else {}
    return found


def read_key(message: dict[str, Any], arguments: dict[str, dict[str, Any]]) -> tuple:
    args = arguments.get(message.get("tool_call_id"), {})
    return tuple(args.get(field) for field in READ_KEY_FIELDS)


def superseded_reads(messages: list[dict[str, Any]]) -> set[int]:
    """Indexes of read_file results that a later read of the same file and range replaces."""
    arguments = call_arguments(messages)
    latest: dict[tuple, int] = {}
    stale: set[int] = set()
    for index, message in enumerate(messages):
        if message.get("role") == "tool" and message.get("name") == READ_TOOL:
            key = read_key(message, arguments)
            if key in latest:
                stale.add(latest[key])
            latest[key] = index
    return stale


def summarized(message: dict[str, Any]) -> dict[str, Any]:
    content = message.get("content") or ""
    if content.startswith(COMPACTED_PREFIX):
        return message
    return {**message, "content": COMPACTED_PREFIX + summarize_result(message.get("name") or "", content)}


def compactable(messages: list[dict[str, Any]], keep_rounds: int, reads: bool) -> list[int]:
    """Tool results before the last `keep_rounds` rounds, reads or non-reads, oldest first."""
    starts = round_starts(messages)
    if len(starts) <= keep_rounds:
        return []
    cutoff = starts[-keep_rounds] if keep_rounds else len(messages)
    return [
        i for i, m in enumerate(messages[:cutoff])
        if m.get("role") == "tool" and (m.get("name") == READ_TOOL) == reads
    ]


def compact_tool_history(
    messages: list[dict[str, Any]],
    keep_rounds: int = KEEP_FULL_ROUNDS,
    trigger_chars: int = COMPACT_TRIGGER_CHARS,
    target_chars: int = COMPACT_TARGET_CHARS,
) -> list[dict[str, Any]]:
    """Copy of `messages`, unchanged up to `trigger_chars`; past it, summarized oldest-first down to `target_chars`."""
    if history_chars(messages) <= trigger_chars:
        return list(messages)
    stale = superseded_reads(messages)
    compacted = [summarized(m) if i in stale else m for i, m in enumerate(messages)]
    for reads in (False, True):
        for index in compactable(compacted, keep_rounds, reads):
            if history_chars(compacted) <= target_chars:
                break
            compacted[index] = summarized(compacted[index])
    return compacted


def is_state_message(message: dict[str, Any]) -> bool:
    return message.get("role") == STATE_ROLE and str(message.get("content") or "").startswith(STATE_HEADING)


def add_working_state(messages: list[dict[str, Any]], state: str) -> None:
    """Append `state` to the live request messages when it differs from the last state sent.

    Earlier state messages stay where they are: removing one would make the next request stop extending the
    previous one, and servers that cannot rewind a recurrent model's cache would process the whole prompt again.
    """
    if not state:
        return
    previous = next((m.get("content") for m in reversed(messages) if is_state_message(m)), None)
    if previous != state:
        messages.append({"role": STATE_ROLE, "content": state})
