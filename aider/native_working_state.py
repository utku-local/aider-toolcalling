"""Builds the structured working state the agent sees with every request, from the operation ledger.
It lists files read and changed, recent commands with exit codes and recent failures, using only operations the
ledger marks executed or failed; the chat history is never used to decide what happened.
This keeps the essentials available after old tool results have been compacted out of the history.
"""

import json
from typing import Any

from aider.native_tool_ledger import CHANGE_TOOLS, OperationRecord, OperationStatus
from aider.native_tool_summary import exit_code, first_line

READ_TOOLS = frozenset({"read_file"})
COMMAND_TOOL = "run_command"
MAX_LISTED_FILES = 20
MAX_LISTED_COMMANDS = 5
MAX_LISTED_FAILURES = 3
STATE_HEADING = "## Working state (from the operation log; authoritative)"
EMPTY_STATE = ""
NO_TASKS = ""


def argument(record: OperationRecord, name: str) -> Any:
    try:
        return json.loads(record.arguments).get(name)
    except (ValueError, AttributeError):
        return None


def unique_recent(values: list[str], limit: int) -> list[str]:
    seen: list[str] = []
    for value in reversed(values):
        if value and value not in seen:
            seen.append(value)
    return list(reversed(seen[:limit]))


def command_lines(records: list[OperationRecord]) -> list[str]:
    commands = [r for r in records if r.tool == COMMAND_TOOL and r.status is OperationStatus.EXECUTED]
    return [
        f"- `{argument(r, 'command')}` -> exit {exit_code(r.result)}"
        for r in commands[-MAX_LISTED_COMMANDS:]
    ]


def render_working_state(records: list[OperationRecord], open_tasks: str = NO_TASKS) -> str:
    """Markdown block for the system prompt; empty when nothing has run and no task is open."""
    executed = [r for r in records if r.status is OperationStatus.EXECUTED]
    read = unique_recent([argument(r, "path") for r in executed if r.tool in READ_TOOLS], MAX_LISTED_FILES)
    changed = unique_recent(
        [argument(r, "path") for r in executed if r.tool in CHANGE_TOOLS], MAX_LISTED_FILES
    )
    denied = [r for r in records if r.status is OperationStatus.DENIED]
    failed = [r for r in records if r.status is OperationStatus.FAILED][-MAX_LISTED_FAILURES:]

    sections = []
    if open_tasks:
        sections.append("Task list:\n" + open_tasks)
    if changed:
        sections.append("Files changed: " + ", ".join(changed))
    if read:
        sections.append("Files read: " + ", ".join(read))
    if command_lines(records):
        sections.append("Commands run:\n" + "\n".join(command_lines(records)))
    if denied:
        sections.append(f"Declined by the user: {len(denied)} operation(s); do not retry them unchanged.")
    if failed:
        sections.append(
            "Recent tool errors:\n" + "\n".join(f"- {r.tool}: {first_line(r.result)}" for r in failed)
        )
    if not sections:
        return EMPTY_STATE
    return STATE_HEADING + "\n" + "\n".join(sections)
