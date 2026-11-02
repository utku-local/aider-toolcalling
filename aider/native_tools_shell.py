"""The run_command tool: runs one shell command in the project root after EXECUTE approval.
Commands get a timeout and only the tail of their combined output is returned, so a noisy build cannot flood
the context window.
The user must approve every command; Aider's --yes-always does not approve commands on its own.
"""

import subprocess
from typing import Union

from aider.native_environment import command_hint, no_match_hint
from aider.native_command_policy import PolicyAction, Risk, without_stderr_merge
from aider.native_root_cd import without_root_cd
from aider.native_tool_context import DENIED_ACTION, ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolRegistry

DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
MAX_OUTPUT_CHARS = 20_000
OUTPUT_TRUNCATED = "[output truncated; showing the last part]\n"
NO_OUTPUT = "(no output)"
POLICY_REFUSAL = "Refused by the command policy: "
SPILL_LABEL = "command"
AUTHORIZED = ""

RUN_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "timeout_seconds": {
            "type": "integer",
            "description": f"Seconds before the command is stopped (default {DEFAULT_TIMEOUT_SECONDS}, "
            f"max {MAX_TIMEOUT_SECONDS}).",
        },
    },
    "required": ["command"],
}


def output_tail(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text or NO_OUTPUT
    return OUTPUT_TRUNCATED + text[-MAX_OUTPUT_CHARS:]


def as_text(value: Union[str, bytes, None]) -> str:
    """Partial output of a timed-out process may be bytes even in text mode."""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value or ""


def clamp_timeout(timeout_seconds: int) -> int:
    return max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))


def approval_title(risks: frozenset[Risk]) -> str:
    if not risks:
        return "Run this command?"
    return "Run this command? Risks: " + "; ".join(sorted(risk.value for risk in risks))


def authorize(ctx: ToolContext, command: str) -> str:
    """Apply the command policy and, when needed, ask; returns a refusal message, or "" to proceed."""
    decision = ctx.check_command(command)
    if decision.action is PolicyAction.DENY:
        return f"{POLICY_REFUSAL}{decision.reason}"
    if decision.action is PolicyAction.ASK and not ctx.approve(
        ToolPermission.EXECUTE, approval_title(decision.risks), command
    ):
        return DENIED_ACTION
    return AUTHORIZED


def run_command(ctx: ToolContext, command: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    command = without_stderr_merge(without_root_cd(command, ctx.root))
    refusal = authorize(ctx, command)
    if refusal:
        return refusal
    timeout = clamp_timeout(timeout_seconds)
    try:
        completed = subprocess.run(
            ctx.wrap_command(command),
            cwd=ctx.root,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as err:
        partial = as_text(err.stdout) + as_text(err.stderr)
        return f"Command timed out after {timeout} seconds.\n{output_tail(partial)}"
    combined = (completed.stdout or "") + (completed.stderr or "")
    shown = ctx.spill.shorten(combined, SPILL_LABEL) if ctx.spill and len(combined) > MAX_OUTPUT_CHARS \
        else output_tail(combined)
    result = f"Exit code: {completed.returncode}\n{shown}"
    hint = command_hint(combined, ctx.sandboxed) if completed.returncode else ""
    hint = hint or no_match_hint(command, completed.returncode, combined)
    return f"{result}\n{hint}" if hint else result


def register_shell_tools(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add run_command, bound to `ctx`, to `registry`."""
    registry.register(
        "run_command",
        "Run a shell command in the project root; stdout and stderr are captured, so add no pipes or redirections.",
        RUN_PARAMETERS,
        lambda command, timeout_seconds=DEFAULT_TIMEOUT_SECONDS: run_command(
            ctx, command, timeout_seconds
        ),
    )
