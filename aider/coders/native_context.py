"""Replaces old tool rounds with a model-written summary when a request's history grows past the trigger.
The summary goes into the live request list and into cur_messages, so later requests extend it and the next turn
starts from it; the last rounds stay verbatim.
When the model cannot write a summary, nothing changes and the usual one-line compaction still applies.
"""

from typing import Any

from aider.native_context_summary import (
    needs_summary,
    replace_span,
    same_tail_start,
    summary_request,
    summary_span,
)
from aider.native_tool_compaction import round_starts

SUMMARIZING = "Summarizing {count} earlier tool rounds to keep the context small..."


def maybe_summarize(coder: Any, messages: list[dict[str, Any]]) -> bool:
    """Summarize old rounds of `messages` in place when it is too long; True when a summary was written."""
    if not needs_summary(messages):
        return False
    start, end = summary_span(messages)
    coder.io.tool_output(SUMMARIZING.format(count=len(round_starts(messages[start:end]))))
    try:
        summary = coder.main_model.simple_send_with_retries(summary_request(messages[start:end]))
    except Exception as err:  # any provider error: keep the history and fall back to compaction
        coder.io.tool_warning(f"Could not summarize earlier rounds: {err}")
        return False
    if not summary or not summary.strip():
        return False
    tail = messages[end:]
    replace_span(messages, start, end, summary)
    cur = coder.cur_messages
    cur_starts = round_starts(cur)
    tail_at = same_tail_start(cur, tail)
    if cur_starts and tail_at is not None and cur_starts[0] < tail_at:
        replace_span(cur, cur_starts[0], tail_at, summary)
    return True
