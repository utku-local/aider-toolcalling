"""Builds the factual footer added to a task sub-agent's report, from the operation ledger.
A sub-agent's report is the only thing the main agent sees of its work, and a local model asked to "run this and
show me the output" has answered with output it worked out in its head when the command could not run.
The footer lists the commands that really ran with their exit codes, the ones that did not, and the files changed,
so the main agent can tell a real run from a described one; it uses only ledger records, never the report text.
"""

from aider.native_tool_ledger import CHANGE_TOOLS, OperationRecord, OperationStatus
from aider.native_working_state import COMMAND_TOOL, MAX_LISTED_FILES, argument, command_lines, unique_recent

FOOTER_HEADING = "[From the operation log of this task, not written by the sub-agent]"
NO_COMMAND_RAN = (
    "No command ran in this task. Any command output in the report above did not come from a real run; do not "
    "treat it as verification."
)
COMMANDS_RAN = "Commands that ran:"
COMMANDS_NOT_RUN = "Commands requested but not run (not approved, refused or failed to start): {count}"
FILES_CHANGED = "Files changed: {files}"


def task_footer(records: list[OperationRecord]) -> str:
    """The footer for a task whose calls are `records`; it always states whether any command really ran."""
    executed = [r for r in records if r.status is OperationStatus.EXECUTED]
    lines = [FOOTER_HEADING]
    ran = command_lines(records)
    lines += [COMMANDS_RAN, *ran] if ran else [NO_COMMAND_RAN]
    not_run = [r for r in records if r.tool == COMMAND_TOOL and r.status is not OperationStatus.EXECUTED]
    if not_run:
        lines.append(COMMANDS_NOT_RUN.format(count=len(not_run)))
    changed = unique_recent([argument(r, "path") for r in executed if r.tool in CHANGE_TOOLS], MAX_LISTED_FILES)
    if changed:
        lines.append(FILES_CHANGED.format(files=", ".join(changed)))
    return "\n".join(lines)
