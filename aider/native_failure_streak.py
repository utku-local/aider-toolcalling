"""Detects a run of commands that keep failing with the same error while no file changes in between.
Measured on the 27B (expert eval, expr-eval): it wrote a parser with a fault, then ran probe after probe that each
ended in the same EvalError, decided the code was right and blamed stale bytecode, until the task timed out.
Another probe cannot show anything new, so the note sends the model back to the code that raises the error.
The check reads only the operation ledger of the current request.
"""

from aider.native_tool_ledger import CHANGE_TOOLS, OperationLedger
from aider.native_tool_summary import exit_code, last_line

COMMAND_TOOL = "run_command"
SAME_ERROR_LIMIT = 3
SAME_ERROR_NOTE = (
    "\nNote: the last {count} commands all failed with the same error and no file changed in between:\n  {error}\n"
    "Another probe will end the same way, and stale caches are not the cause. The fault is in the code: find where "
    "this error is raised (search_code for its text), read that function and its callers in full, fix the logic, "
    "then run the tests again."
)


def same_error_streak(ledger: OperationLedger) -> tuple[int, str]:
    """How many of the latest commands failed with one identical last output line, and that line.

    Counting goes back from the newest operation of the current request and stops at a file change, a command
    that passed, or a different error; (0, "") when the latest command did not fail."""
    count, error = 0, ""
    for record in reversed(ledger.executed()):
        if record.request != ledger.request or record.tool in CHANGE_TOOLS:
            break
        if record.tool != COMMAND_TOOL:
            continue
        line = last_line(record.result)
        if not exit_code(record.result) or (count and line != error):
            break
        count, error = count + 1, line
    return count, error


def same_error_note(ledger: OperationLedger) -> str:
    """SAME_ERROR_NOTE once the streak reaches SAME_ERROR_LIMIT; empty before that."""
    count, error = same_error_streak(ledger)
    return SAME_ERROR_NOTE.format(count=count, error=error) if count >= SAME_ERROR_LIMIT else ""
