"""Detects and trims a runaway repetition loop in a model's streamed reply.
A degenerate decoder can emit the same line over and over until it reaches the token limit, wasting the whole budget
on garbage; this watches the growing reply and reports when its trailing lines have collapsed into one identical line
repeated past a safe threshold. The caller trims the reply to a single copy and stops reading the stream; this module
does no I/O and keeps no state between calls.
"""

from typing import List, Tuple

NEWLINE = "\n"
# A line must repeat at least this many times in a row, and have at least this many non-blank characters, before it
# counts as a runaway loop. Both are set high enough that ordinary repeated code or markup lines do not trip it.
MIN_REPEATS = 6
MIN_UNIT_CHARS = 16
# Detection scans only this many trailing characters, so the cost per streamed chunk stays constant however long the
# whole reply grows. A loop trips the first time it reaches MIN_REPEATS, when every copy still fits in this window.
TAIL_WINDOW = 4000


def collapse_runaway_repetition(text: str) -> Tuple[str, bool]:
    """Return (text, tripped). When the reply's trailing completed lines are one identical, non-trivial line repeated
    at least MIN_REPEATS times, the extra copies are removed so a single copy remains and tripped is True; otherwise
    the text is returned unchanged with tripped False. Only the last TAIL_WINDOW characters are examined."""
    if len(text) <= TAIL_WINDOW:
        head, window = "", text
    else:
        head, window = text[:-TAIL_WINDOW], text[-TAIL_WINDOW:]
    collapsed, tripped = _collapse_lines(window)
    if not tripped:
        return text, False
    return head + collapsed, True


def _collapse_lines(window: str) -> Tuple[str, bool]:
    """Trim a trailing run of one identical completed line within `window`; see collapse_runaway_repetition."""
    lines = window.split(NEWLINE)
    # The final segment is still being streamed and has no newline yet, so only earlier, completed lines are compared.
    completed = lines[:-1]
    if not completed:
        return window, False
    unit = completed[-1]
    if len(unit.strip()) < MIN_UNIT_CHARS:
        return window, False
    run = _trailing_identical_run(completed, unit)
    if run < MIN_REPEATS:
        return window, False
    kept = completed[: len(completed) - run] + [unit]
    return NEWLINE.join(kept) + NEWLINE, True


def _trailing_identical_run(completed: List[str], unit: str) -> int:
    """How many entries at the end of `completed` equal `unit`, counting back until one differs."""
    run = 0
    for segment in reversed(completed):
        if segment != unit:
            break
        run += 1
    return run
