"""Model-written summary of earlier tool rounds, replacing them in the live request history when it grows too long.
The model reads a bounded transcript of the old rounds and writes what a successor needs: the goal, findings, files
changed and why, commands and results, and what remains; the last rounds stay verbatim so tool pairs stay valid.
The summary is written into the live message list, so later requests extend it and a prefix cache stays warm.
"""

import json
from typing import Any, Optional

from aider.native_tool_compaction import history_chars, round_starts

SUMMARY_TRIGGER_CHARS = 192_000
KEEP_ROUNDS = 2
MAX_RESULT_CHARS = 2_000
MAX_TRANSCRIPT_CHARS = 120_000
SUMMARY_HEADING = "## Summary of earlier work in this request (written by you; the rounds it covers were removed)\n"
SUMMARY_SYSTEM = (
    "You are summarizing your own earlier work as a coding agent so you can continue it with less context. "
    "Write a concise but specific summary with these parts: Goal; What I found (file paths, function names, "
    "error messages, test results); Changes made (each file and why); Commands run and their outcome; "
    "Open problems and next steps. Keep exact names and numbers. Do not invent anything."
)
CUT_NOTE = "\n[... cut ...]"


def summary_span(messages: list[dict[str, Any]], keep_rounds: int = KEEP_ROUNDS) -> Optional[tuple[int, int]]:
    """Start and end of the old rounds to summarize: from the first tool round to the last `keep_rounds`."""
    starts = round_starts(messages)
    if len(starts) <= keep_rounds:
        return None
    return starts[0], starts[-keep_rounds]


def needs_summary(messages: list[dict[str, Any]], trigger: int = SUMMARY_TRIGGER_CHARS) -> bool:
    return history_chars(messages) > trigger and summary_span(messages) is not None


def render_message(message: dict[str, Any]) -> str:
    role = message.get("role", "")
    content = str(message.get("content") or "")
    if role == "tool":
        body = content if len(content) <= MAX_RESULT_CHARS else content[:MAX_RESULT_CHARS] + CUT_NOTE
        return f"[result of {message.get('name', 'tool')}]\n{body}"
    calls = [
        f"[call {c.get('function', {}).get('name')} {c.get('function', {}).get('arguments')}]"
        for c in message.get("tool_calls") or []
    ]
    return "\n".join(part for part in [f"[{role}] {content}".strip() if content else "", *calls] if part)


def transcript(segment: list[dict[str, Any]]) -> str:
    """The segment as plain text, with long results cut and the whole bounded (newest parts kept)."""
    text = "\n\n".join(render_message(m) for m in segment)
    return text if len(text) <= MAX_TRANSCRIPT_CHARS else CUT_NOTE + text[-MAX_TRANSCRIPT_CHARS:]


def summary_request(segment: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"role": "system", "content": SUMMARY_SYSTEM}, {"role": "user", "content": transcript(segment)}]


def summary_message(summary: str) -> dict[str, Any]:
    return {"role": "user", "content": SUMMARY_HEADING + summary.strip()}


def replace_span(messages: list[dict[str, Any]], start: int, end: int, summary: str) -> None:
    """Replace messages[start:end] in place with one summary message."""
    messages[start:end] = [summary_message(summary)]


def same_tail_start(cur: list[dict[str, Any]], tail: list[dict[str, Any]]) -> Optional[int]:
    """Index in `cur` where `tail` (the kept rounds) begins, matched by content; None when it is not there."""
    key = json.dumps(tail, sort_keys=True, default=str)
    for start in range(len(cur) - len(tail), -1, -1):
        if json.dumps(cur[start:start + len(tail)], sort_keys=True, default=str) == key:
            return start
    return None
