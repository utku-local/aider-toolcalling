"""User hooks around tool calls: shell commands from .aider-agent.json run before or after matching tools.
A before hook that exits non-zero blocks the call and its output tells the model why; an after hook's output is
appended to the result as a note. Hooks see the tool name, its arguments and (after) its result in the environment.
Running a command is injected, so the matching and the decisions here are pure and testable.
"""

import re
from dataclasses import dataclass
from typing import Callable

# Runs a hook command with extra environment variables and returns its exit code and combined output.
RunHook = Callable[[str, dict[str, str]], tuple[int, str]]
ENV_TOOL = "AIDER_TOOL"
ENV_ARGS = "AIDER_TOOL_ARGS"
ENV_RESULT = "AIDER_TOOL_RESULT"
MAX_ENV_RESULT_CHARS = 20_000
MAX_NOTE_CHARS = 4_000
SUCCESS = 0
BLOCKED = "Error: blocked by a project hook ({command}): {output}"
NO_OUTPUT = "(no output)"
NOTE = "\n[hook {command}] {output}"


@dataclass(frozen=True)
class HookRule:
    """A command run for tools whose name fully matches `tools` (a regular expression such as edit_file|write_file)."""

    tools: str
    command: str

    def matches(self, tool: str) -> bool:
        return re.fullmatch(self.tools, tool) is not None


@dataclass(frozen=True)
class ToolHooks:
    before: tuple[HookRule, ...]
    after: tuple[HookRule, ...]
    run: RunHook


def hook_env(tool: str, arguments: str, result: str = "") -> dict[str, str]:
    env = {ENV_TOOL: tool, ENV_ARGS: arguments}
    if result:
        env[ENV_RESULT] = result[:MAX_ENV_RESULT_CHARS]
    return env


def blocked_by(hooks: ToolHooks, tool: str, arguments: str) -> str:
    """The refusal from the first matching before hook that fails; empty when every hook passes."""
    for rule in hooks.before:
        if rule.matches(tool):
            code, output = hooks.run(rule.command, hook_env(tool, arguments))
            if code != SUCCESS:
                return BLOCKED.format(command=rule.command, output=(output.strip() or NO_OUTPUT)[:MAX_NOTE_CHARS])
    return ""


def after_notes(hooks: ToolHooks, tool: str, arguments: str, result: str) -> str:
    """Notes from the matching after hooks that printed something, to append to the result."""
    notes = []
    for rule in hooks.after:
        if rule.matches(tool):
            _, output = hooks.run(rule.command, hook_env(tool, arguments, result))
            if output.strip():
                notes.append(NOTE.format(command=rule.command, output=output.strip()[:MAX_NOTE_CHARS]))
    return "".join(notes)
