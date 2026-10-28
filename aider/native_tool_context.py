"""Shared context handed to native tools: project root, file listing, approval and edit tracking.
Tools receive callables instead of Aider's io or Coder objects, so each tool module stays a thin adapter
that can be tested with plain functions.
ToolPermission names the approval level a tool needs before it may act.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from aider.native_command_policy import PolicyAction, PolicyDecision
from aider.native_sandbox import shell_argv
from aider.native_todo import TodoList


class ToolPermission(str, Enum):
    """READ runs without asking; WRITE, EXECUTE, NETWORK, SENSITIVE (reading secrets) and MCP need approval."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    NETWORK = "network"
    SENSITIVE = "sensitive"
    MCP = "mcp"


DENIED_CHANGE = "The user declined this change. Ask them how to proceed or try a different approach."
DENIED_ACTION = "The user declined this action. Ask them how to proceed or try a different approach."


def ask_for_every_command(command: str) -> PolicyDecision:
    """Default policy when none is configured: every command needs approval."""
    return PolicyDecision(PolicyAction.ASK)


def ignore_path(path: str) -> None:
    """Default before-write hook: no snapshot."""


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool may touch. `approve(permission, title, details)` returns True to proceed.

    Defaults: `check_command` asks for every command, `before_write` keeps no snapshot, `todos` starts empty,
    `wrap_command` runs a command through /bin/sh without a sandbox.
    """

    root: Path
    list_files: Callable[[], list[str]]
    find_tags: Callable[[str, str], list[Any]]
    approve: Callable[[ToolPermission, str, str], bool]
    on_edit: Callable[[str], None]
    dry_run: bool
    check_command: Callable[[str], PolicyDecision] = ask_for_every_command
    before_write: Callable[[str], None] = ignore_path
    todos: TodoList = field(default_factory=TodoList)
    wrap_command: Callable[[str], list[str]] = shell_argv
