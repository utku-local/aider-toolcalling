"""Pure scoring of one scenario run from the agent's operation log: order, error handling, tokens and success.
Order checks plan, inspect, test and verify against the real call sequence; error handling classifies what the
agent did right after each failed call; task success is decided separately by the runner from the project itself.
Only executed calls count as work done, so a declined or refused command never counts as a test that ran.
"""

import re
from typing import Callable

Call = dict[str, str]

EXECUTED = "executed"
GATE_MARKER = "Error: plan first"
CHANGE_TOOLS = frozenset({"edit_file", "multi_edit", "write_file"})
INSPECT_TOOLS = frozenset({"read_file", "search_code", "find_symbol", "find_files", "list_files", "git", "research"})
TEST_WORDS = ("unittest", "pytest")
PORT_CHECK_WORDS = ("lsof", "pgrep")
TOKEN_LINE = re.compile(r"^Tokens: .*$", re.M)
TOKENS = re.compile(r"([\d.]+)(k?) (sent|received)")
EXIT = re.compile(r"Exit code: (-?\d+)")
PATH = re.compile(r"[\w./-]+\.(?:py|toml|md)")
THOUSAND = 1000
NO_EXIT = -1
SUCCESS_EXIT = 0
ORDER_STEPS = 4


def token_counts(log: str) -> tuple[int, int]:
    """Sum of the 'Tokens: Nk sent, M received' lines of an agent log."""
    sent = received = 0
    for amount, unit, kind in TOKENS.findall("\n".join(TOKEN_LINE.findall(log))):
        value = int(float(amount) * (THOUSAND if unit == "k" else 1))
        if kind == "sent":
            sent += value
        else:
            received += value
    return sent, received


def first_index(calls: list[Call], predicate: Callable[[Call], bool]) -> int:
    return next((i for i, c in enumerate(calls) if predicate(c)), NO_EXIT)


def is_change(call: Call) -> bool:
    return call["tool"] in CHANGE_TOOLS and call["status"] == EXECUTED


def is_test_run(call: Call) -> bool:
    """A test command that actually executed."""
    return (call["tool"] == "run_command" and call["status"] == EXECUTED
            and any(word in call["args"] for word in TEST_WORDS))


def exit_code(call: Call) -> int:
    match = EXIT.search(call["result"])
    return int(match.group(1)) if match else NO_EXIT


def failed(call: Call) -> bool:
    """A command that exited non-zero or a tool error; the plan-first gate is guidance, not a failure."""
    if call["result"].startswith(GATE_MARKER):
        return False
    return (call["tool"] == "run_command" and exit_code(call) not in (SUCCESS_EXIT, NO_EXIT)) or call[
        "result"
    ].startswith("Error")


def order_score(calls: list[Call]) -> dict:
    """Plan -> inspect -> act -> test -> verify, each judged on the real sequence."""
    plan = first_index(calls, lambda c: c["tool"] == "todo_write")
    change = first_index(calls, is_change)
    changes = [i for i, c in enumerate(calls) if is_change(c)]
    tests = [i for i, c in enumerate(calls) if is_test_run(c)]
    steps = {
        "planned_before_change": plan != NO_EXIT and change != NO_EXIT and plan < change,
        "inspected_before_change": change != NO_EXIT and any(c["tool"] in INSPECT_TOOLS for c in calls[:change]),
        "tested_after_change": bool(changes) and any(i > changes[0] for i in tests),
        "verified_after_last_change": bool(changes)
        and any(i > changes[-1] and exit_code(calls[i]) == SUCCESS_EXIT for i in tests),
    }
    gated = any(c["result"].startswith(GATE_MARKER) for c in calls)
    return {**steps, "order_points": f"{sum(steps.values())}/{ORDER_STEPS}", "plan_only_after_gate": gated}


def mentioned_paths(text: str) -> set[str]:
    return set(PATH.findall(text))


def error_handling(calls: list[Call]) -> dict:
    """After each failure: inspected something, changed code it had read or the error named, repeated the same
    call, or changed code it never looked at (a guess)."""
    counts = {"examined_error": 0, "informed_change": 0, "repeated_same_call": 0, "guessed": 0, "other": 0}
    for i, call in enumerate(calls[:-1]):
        if not failed(call):
            continue
        nxt = calls[i + 1]
        read = [c["args"] for c in calls[: i + 1] if c["tool"] == "read_file"]
        known = mentioned_paths(call["result"]) | {p for args in read for p in mentioned_paths(args)}
        if nxt["tool"] == call["tool"] and nxt["args"] == call["args"]:
            counts["repeated_same_call"] += 1
        elif nxt["tool"] in INSPECT_TOOLS or nxt["tool"] == "run_command":
            counts["examined_error"] += 1
        elif nxt["tool"] in CHANGE_TOOLS:
            counts["informed_change" if any(p in nxt["args"] for p in known) else "guessed"] += 1
        else:
            counts["other"] += 1
    return {"failures": sum(counts.values()), **counts}


def service_outcome(calls: list[Call], answer: str, code_changed: bool, start_hint: str) -> dict:
    """The service scenario passes when no code changed and the agent either told the user how to start the
    server or started it itself."""
    told = start_hint in answer
    started = any(c["tool"] == "start_background" and c["status"] == EXECUTED for c in calls)
    checked = any(c["tool"] == "run_command" and any(w in c["args"] for w in PORT_CHECK_WORDS) for c in calls)
    return {"checked_listening_port": checked, "changed_code": code_changed, "told_user_to_start_server": told,
            "started_server_itself": started, "success": (told or started) and not code_changed}
