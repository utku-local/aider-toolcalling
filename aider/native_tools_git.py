"""Read-only git tool: status, diff, log, show and blame without approval and without a shell.
Subcommands and flags come from an allow list, refs and paths cannot start with "-", paths must stay inside the
project, and pagers, external diff drivers and textconv filters are disabled so repo config cannot run programs.
Anything that would change the repository or reach a remote goes through run_command and its approval instead.
"""

import os
import subprocess
from typing import Optional

from aider.native_tool_context import ToolContext
from aider.native_toolcalling import NativeToolError, NativeToolRegistry
from aider.native_tools_builtin import resolve_in_root
from aider.native_tools_shell import output_tail

GIT_TIMEOUT_SECONDS = 30
SAFE_CONFIG = ("-c", "core.pager=cat", "-c", "core.fsmonitor=false", "-c", "diff.external=")
SUBCOMMAND_FLAGS = {
    "status": frozenset({"--short", "--porcelain", "--branch", "-s", "-b"}),
    "diff": frozenset({"--stat", "--name-only", "--name-status", "--cached", "--staged", "-U0", "-U3"}),
    "log": frozenset({"--oneline", "--stat", "--name-only", "-p", "--patch", "-n", "--graph", "--all"}),
    "show": frozenset({"--stat", "--name-only", "--oneline", "-p"}),
    "blame": frozenset({"-L", "-w"}),
}
NO_EXTERNAL = {"diff": ("--no-ext-diff", "--no-textconv"), "log": ("--no-ext-diff", "--no-textconv"),
               "show": ("--no-ext-diff", "--no-textconv")}
VALUE_FLAGS = frozenset({"-n", "-L"})
SEPARATOR = "--"
# Only the repository's own config applies: global and system config could define pagers or diff drivers.
GIT_ENV = {
    "GIT_PAGER": "cat",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "PATH": os.defpath,
}

GIT_PARAMETERS = {
    "type": "object",
    "properties": {
        "subcommand": {"type": "string", "description": "One of: status, diff, log, show, blame."},
        "args": {
            "type": "array",
            "description": "Extra arguments: allowed flags (e.g. --stat, --cached, --oneline, -n 5), "
            "refs, and paths after '--'.",
        },
    },
    "required": ["subcommand"],
}


class GitToolError(NativeToolError):
    """Raised for subcommands or arguments the read-only git tool does not allow."""


def check_args(ctx: ToolContext, subcommand: str, args: list[str]) -> None:
    allowed = SUBCOMMAND_FLAGS.get(subcommand)
    if allowed is None:
        raise GitToolError(f"Unsupported subcommand {subcommand!r}; use one of {sorted(SUBCOMMAND_FLAGS)}")
    after_separator, expect_value = False, False
    for arg in args:
        if not isinstance(arg, str):
            raise GitToolError("Arguments must be strings")
        if expect_value:
            expect_value = False
        elif arg == SEPARATOR:
            after_separator = True
        elif after_separator:
            resolve_in_root(ctx.root, arg)
        elif arg.startswith("-"):
            if arg not in allowed:
                raise GitToolError(f"Flag {arg!r} is not allowed for git {subcommand}")
            expect_value = arg in VALUE_FLAGS


def git(ctx: ToolContext, subcommand: str, args: Optional[list[str]] = None) -> str:
    args = list(args or [])
    check_args(ctx, subcommand, args)
    command = ["git", *SAFE_CONFIG, subcommand, *NO_EXTERNAL.get(subcommand, ()), *args]
    try:
        done = subprocess.run(
            command, cwd=ctx.root, capture_output=True, text=True, errors="replace",
            timeout=GIT_TIMEOUT_SECONDS, env=GIT_ENV,
        )
    except subprocess.TimeoutExpired as err:
        raise GitToolError(f"git {subcommand} timed out after {GIT_TIMEOUT_SECONDS} seconds") from err
    return f"Exit code: {done.returncode}\n{output_tail(done.stdout + done.stderr)}"


def register_git_tool(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add the read-only git tool, bound to `ctx`, to `registry`."""
    registry.register(
        "git",
        "Inspect the repository without changing it: status, diff, log, show or blame.",
        GIT_PARAMETERS,
        lambda subcommand, args=None: git(ctx, subcommand, args),
    )
