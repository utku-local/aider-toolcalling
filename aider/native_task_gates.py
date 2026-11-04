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


# Openers of a first-person promise of imminent work, paired with an action verb below. Measured: a local model
# ended turns with "Now let me verify my changes and move on to items 4, 5, 6" and made no tool call, so the turn
# finished as if the work were done; after the repeat stop it answered "sorry, stuck in a loop, I'll fix it now"
# every time the user asked. A no-tool-call reply that only promises is sent back once.
ACTION_OPENERS = (
    "let me ", "let me now ", "i'll ", "i'll now ", "i will ", "i will now ", "now i'll ", "now i will ",
    "now let me ", "i'm going to ", "i am going to ", "next i'll ", "next, i'll ", "let me go ahead and ",
)
ACTION_VERBS = (
    "verify", "run", "check", "fix", "update", "make", "continue", "start", "do ", "implement", "add", "edit",
    "create", "write", "work", "go ", "proceed", "test", "rerun", "re-run", "apply", "patch", "look",
    "investigate", "try", "move on",
)
# Promises that already carry their own verb, so they stand alone.
ACTION_STANDALONE = ("working on it", "will work on", "on it now", "fix it now", "get to work", "stuck in a loop")
ACTION_PHRASES = frozenset(
    [opener + verb for opener in ACTION_OPENERS for verb in ACTION_VERBS] + list(ACTION_STANDALONE)
)
# A reply with no text and no tool call. mlx_vlm answers this way when it rejects a malformed tool call (measured: a
# 20-minute session ended at a rejected todo_write with nothing saved), so the model gets to try again; the cap stops
# a server that only ever answers empty from looping.
MAX_EMPTY_REPLY_RETRIES = 2
EMPTY_REPLY_NUDGE = (
    "Your last reply came back empty: no text and no tool call reached the user, possibly because a tool call was "
    "malformed. Nothing happened. Make the next tool call again, or give your answer."
)
ACTION_PROMISE_NUDGE = (
    "You said you would continue but made no tool call, so nothing happened. Either do it now with a tool call, or "
    "tell the user plainly what is done, what is left, and what is blocking you. Do not say you will work on it later."
)


def announces_action(text: str) -> bool:
    """True when a no-tool-call reply ends by promising imminent self-action instead of reporting or asking.
    A weak local model often narrates its next step ('let me verify and move on', 'I'll fix it now') or, after the
    repeat stop, says it is stuck and will fix it, without calling a tool; that must not count as a finished answer.
    A trailing question is a genuine hand-back, so it never counts."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return False
    tail = lines[-1].lower()
    if tail.endswith("?"):
        return False
    return any(phrase in tail for phrase in ACTION_PHRASES)


def may_retry_empty(text: str, retries_used: int) -> bool:
    """Whether a reply with this visible text is empty and still has a retry left."""
    return not text.strip() and retries_used < MAX_EMPTY_REPLY_RETRIES
