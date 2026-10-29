"""Two checks that keep a local model from skipping the parts of a task it is weakest at: planning and verifying.
Before the first file change of a request that has already explored the project, a model without a task list is
asked once to plan, with a verification step last. When it answers after changing files, it is sent back once if
nothing has passed since its last change or its task list still has open items; both checks read only the ledger.
"""

from aider.native_tool_ledger import CHANGE_TOOLS, OperationLedger, OperationRecord, OperationStatus
from aider.native_tool_summary import exit_code

COMMAND_TOOL = "run_command"
SUCCESS_EXIT = 0
# Exploring calls after which a change needs a plan; a direct one- or two-step fix never does.
PLAN_AFTER_CALLS = 3
PLAN_FIRST_MARKER = "Error: plan first"
PLAN_FIRST = (
    PLAN_FIRST_MARKER + ". Before changing files, use todo_write to write a short plan: what you found, the "
    "changes to make, and, as the last item, how you will check that the result works (a test or command to run). "
    "Then make this change again."
)
UNVERIFIED_GAP = (
    "You changed files, but no command has passed since your last change. Run the tests or a command that "
    "exercises the change; if nothing can check it, say so plainly in your answer."
)
OPEN_TASKS_GAP = "Your task list still has unfinished items:\n{tasks}\nFinish them, or say why they cannot be done."
VERIFY_HEADING = "Before you finish:"


def this_request(ledger: OperationLedger) -> list[OperationRecord]:
    return [r for r in ledger.records if r.request == ledger.request]


def needs_plan(ledger: OperationLedger, tool: str, has_plan: bool) -> bool:
    """True when `tool` would make the request's first file change before any plan, after exploring, and
    plan-first was not asked yet. Once a change has been made, asking for a plan only adds rounds."""
    if tool not in CHANGE_TOOLS or has_plan:
        return False
    records = this_request(ledger)
    asked = any(r.result.startswith(PLAN_FIRST_MARKER) for r in records)
    changed = any(r.tool in CHANGE_TOOLS and r.status is OperationStatus.EXECUTED for r in records)
    return not asked and not changed and len(records) >= PLAN_AFTER_CALLS


def verified_since_change(records: list[OperationRecord]) -> bool:
    """True when the request changed nothing, or a command exited 0 after its last change."""
    executed = [r for r in records if r.status is OperationStatus.EXECUTED]
    changes = [i for i, r in enumerate(executed) if r.tool in CHANGE_TOOLS]
    if not changes:
        return True
    return any(
        r.tool == COMMAND_TOOL and exit_code(r.result) == SUCCESS_EXIT for r in executed[changes[-1] + 1 :]
    )


def completion_nudge(ledger: OperationLedger, open_tasks: str) -> str:
    """What to send back when the model answers with unverified changes or open tasks; empty when it may finish."""
    records = this_request(ledger)
    gaps = []
    if not verified_since_change(records):
        gaps.append(UNVERIFIED_GAP)
    if open_tasks and any(r.tool in CHANGE_TOOLS for r in records):
        gaps.append(OPEN_TASKS_GAP.format(tasks=open_tasks))
    return "\n".join([VERIFY_HEADING] + gaps) if gaps else ""
