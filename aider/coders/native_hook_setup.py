"""Turns the project's configured hooks into the loop's ToolHooks, after the user agrees to run them.
Hooks run shell commands with no per-call approval, so a project's hooks are shown once per session and run only
if the user says yes; unattended runs (--yes-always) never run them, because a cloned repo could define any command.
Each hook runs in the project root through the same wrapper as run_command, so the sandbox applies when enabled.
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Optional

from aider.native_hooks import ToolHooks

HOOK_TIMEOUT_SECONDS = 60
TIMEOUT_CODE = 1
ASK_TITLE = "Run this project's hooks around tool calls in this session?"
TIMED_OUT = "hook timed out after {seconds} s"


def describe_hooks(config: Any) -> str:
    lines = [f"before {r.tools}: {r.command}" for r in config.before_hooks]
    lines += [f"after {r.tools}: {r.command}" for r in config.after_hooks]
    return "\n".join(lines)


Wrap = Callable[[str], list[str]]


def run_hook(wrap: Wrap, root: Path, command: str, env: dict[str, str]) -> tuple[int, str]:
    try:
        done = subprocess.run(wrap(command), cwd=root, env={**os.environ, **env},
                              capture_output=True, text=True, errors="replace", timeout=HOOK_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return TIMEOUT_CODE, TIMED_OUT.format(seconds=HOOK_TIMEOUT_SECONDS)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


def project_hooks(coder: Any, wrap: Wrap) -> Optional[ToolHooks]:
    """The project's hooks if it defines any and the user agrees to run them; None otherwise.

    `wrap` turns a command into argv the way run_command does (sandboxed when the project asks for it)."""
    config = coder.native_agent_config
    if not config.before_hooks and not config.after_hooks:
        return None
    if not coder.io.confirm_ask(ASK_TITLE, subject=describe_hooks(config), explicit_yes_required=True):
        return None
    root = Path(coder.root).resolve()
    return ToolHooks(config.before_hooks, config.after_hooks,
                     lambda command, env: run_hook(wrap, root, command, env))
