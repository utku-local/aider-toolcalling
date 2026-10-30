"""One-line summaries of tool results, for the terminal and for compacted chat history.
A summary keeps what matters later (line counts, match counts, exit codes, the first line of an error) and drops
the bulk, so old rounds stay understandable without their full output.
Exit codes are parsed from the run_command result text; the parser is shared with the working state.
"""

import re
from typing import Optional

EXIT_CODE = re.compile(r"^Exit code: (-?\d+)", re.MULTILINE)
TIMED_OUT = "timed out"
ERROR_PREFIX = "Error: "
MAX_SUMMARY_CHARS = 160
LINE_COUNT_TOOLS = frozenset({"read_file"})
RESULT_COUNT_TOOLS = frozenset({"list_files", "find_files", "search_code", "find_symbol"})
NO_MATCHES = "No matches."
COMMAND_TOOL = "run_command"
REPEAT_NOTE = (
    "Note: you already made this exact call in this request and got the same result; use it and move on "
    "to the next step instead of repeating it.\n"
)


def exit_code(result: str) -> Optional[int]:
    match = EXIT_CODE.search(result)
    return int(match.group(1)) if match else None


def first_line(text: str) -> str:
    line = text.strip().splitlines()[0] if text.strip() else ""
    return line if len(line) <= MAX_SUMMARY_CHARS else line[: MAX_SUMMARY_CHARS - 3] + "..."


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return first_line(lines[-1]) if lines else ""


def summarize_result(tool: str, result: str) -> str:
    """A short, factual description of `result`; never longer than one line."""
    result = result.removeprefix(REPEAT_NOTE)
    if result.startswith(ERROR_PREFIX):
        return first_line(result)
    if tool in LINE_COUNT_TOOLS:
        return f"{len(result.splitlines())} lines"
    if tool in RESULT_COUNT_TOOLS:
        return NO_MATCHES if result.strip() == NO_MATCHES else f"{len(result.splitlines())} results"
    if tool == COMMAND_TOOL:
        code = exit_code(result)
        if code is None:
            return first_line(result)
        tail = last_line(result.split("\n", 1)[1] if "\n" in result else "")
        return f"exit {code}: {tail}" if tail else f"exit {code}"
    return first_line(result)
