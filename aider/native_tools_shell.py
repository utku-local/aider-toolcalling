"""The run_command tool: runs one shell command in the project root after EXECUTE approval.
Commands get a timeout and only the tail of their combined output is returned, so a noisy build cannot flood
the context window.
The user must approve every command; Aider's --yes-always does not approve commands on its own.
"""

import subprocess
from typing import Union

from aider.native_tool_context import ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolRegistry
from aider.native_tools_edit import DENIED_MESSAGE

DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
MAX_OUTPUT_CHARS = 20_000
OUTPUT_TRUNCATED = "[output truncated; showing the last part]\n"
NO_OUTPUT = "(no output)"

RUN_PARAMETERS = {
    "type": "object",
    "properties": {
        "command": {"type": "string", "description": "Shell command to run in the project root."},
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


def run_command(ctx: ToolContext, command: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    if not ctx.approve(ToolPermission.EXECUTE, "Run this command?", command):
        return DENIED_MESSAGE
    timeout = clamp_timeout(timeout_seconds)
    try:
        completed = subprocess.run(
            command,
            shell=True,
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
    return f"Exit code: {completed.returncode}\n{output_tail(combined)}"


def register_shell_tools(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add run_command, bound to `ctx`, to `registry`."""
    registry.register(
        "run_command",
        "Run a shell command (tests, linters, git status, builds) in the project root. "
        "The user approves each command.",
        RUN_PARAMETERS,
        lambda command, timeout_seconds=DEFAULT_TIMEOUT_SECONDS: run_command(
            ctx, command, timeout_seconds
        ),
    )
