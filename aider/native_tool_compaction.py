"""Shrinks tool history before each request and attaches the working state, without changing the stored history.
Both steps keep the request prefix stable so a server-side prefix cache can reuse earlier rounds: the working state
goes in a message at the end, and old tool results are summarized only once the history grows past a size threshold.
Every function returns new lists and dicts, so the full history stays available for later turns and for review.
"""

from typing import Any

from aider.native_tool_summary import summarize_result

KEEP_FULL_ROUNDS = 2
# Compact past ~6K tokens (about 4 characters per token). Measured on real projects, prompt processing dominates
# each round and the local server cannot reuse an extended prefix, so shorter history wins over a stable prefix.
COMPACT_ABOVE_CHARS = 24_000
COMPACTED_PREFIX = "[compacted] "
STATE_ROLE = "user"


def round_starts(messages: list[dict[str, Any]]) -> list[int]:
    """Indexes of assistant messages that requested tools; each starts one tool round."""
    return [
        i for i, m in enumerate(messages) if m.get("role") == "assistant" and m.get("tool_calls")
    ]


def history_chars(messages: list[dict[str, Any]]) -> int:
    return sum(len(m.get("content") or "") for m in messages if isinstance(m.get("content"), str))


def compact_tool_history(
    messages: list[dict[str, Any]],
    keep_rounds: int = KEEP_FULL_ROUNDS,
    min_chars: int = COMPACT_ABOVE_CHARS,
) -> list[dict[str, Any]]:
    """Copy of `messages`; once it exceeds `min_chars`, tool results before the last `keep_rounds` are summarized."""
    starts = round_starts(messages)
    if len(starts) <= keep_rounds or history_chars(messages) <= min_chars:
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
    """Copy of `messages` with `state` as a final message, leaving everything before it unchanged."""
    if not state:
        return list(messages)
    return list(messages) + [{"role": STATE_ROLE, "content": state}]
