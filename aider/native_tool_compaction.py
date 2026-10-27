"""Shrinks tool history before each request and attaches the working state, without changing the stored history.
Tool results of all but the last KEEP_FULL_ROUNDS tool rounds are replaced by one-line summaries; the structured
working state, rendered from the operation ledger, carries the facts those results held.
Every function returns new lists and dicts, so the full history stays available for later turns and for review.
"""

from typing import Any

from aider.native_tool_summary import summarize_result

KEEP_FULL_ROUNDS = 2
COMPACTED_PREFIX = "[compacted] "
SYSTEM_ROLE = "system"
STATE_SEPARATOR = "\n\n"


def round_starts(messages: list[dict[str, Any]]) -> list[int]:
    """Indexes of assistant messages that requested tools; each starts one tool round."""
    return [
        i for i, m in enumerate(messages) if m.get("role") == "assistant" and m.get("tool_calls")
    ]


def compact_tool_history(
    messages: list[dict[str, Any]], keep_rounds: int = KEEP_FULL_ROUNDS
) -> list[dict[str, Any]]:
    """Copy of `messages` where tool results before the last `keep_rounds` rounds are summarized."""
    starts = round_starts(messages)
    if len(starts) <= keep_rounds:
        return list(messages)
    cutoff = starts[-keep_rounds] if keep_rounds else len(messages)
    compacted = []
    for index, message in enumerate(messages):
        content = message.get("content") or ""
        if index < cutoff and message.get("role") == "tool" and not content.startswith(COMPACTED_PREFIX):
            summary = summarize_result(message.get("name") or "", content)
            message = {**message, "content": COMPACTED_PREFIX + summary}
        compacted.append(message)
    return compacted


def with_working_state(messages: list[dict[str, Any]], state: str) -> list[dict[str, Any]]:
    """Copy of `messages` with `state` appended to the first system message (or prepended as one)."""
    if not state:
        return list(messages)
    if messages and messages[0].get("role") == SYSTEM_ROLE:
        first = {**messages[0], "content": (messages[0].get("content") or "") + STATE_SEPARATOR + state}
        return [first] + list(messages[1:])
    return [{"role": SYSTEM_ROLE, "content": state}] + list(messages)
