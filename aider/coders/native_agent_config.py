"""Loads the agent's project configuration from .aider-agent.json in the project root.
It reads command allow and deny rules for the command policy; a missing file means no rules (every command is
asked), and a malformed file is reported once and ignored the same way.
Instruction files such as AGENTS.md are found here too, so the AgentCoder can add them read-only to the chat.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aider.native_command_policy import CommandRule, CommandRules

CONFIG_FILE_NAME = ".aider-agent.json"
INSTRUCTION_FILE_NAMES = ("AGENTS.md", "CLAUDE.md")
MAX_INSTRUCTION_BYTES = 50_000
CONFIG_ENCODING = "utf-8"


@dataclass(frozen=True)
class AgentConfig:
    """Project settings; default: no command rules."""

    rules: CommandRules = CommandRules()


class AgentConfigError(ValueError):
    """Raised when .aider-agent.json does not have the expected shape."""


def parse_rule(raw: Any) -> CommandRule:
    if not isinstance(raw, dict) or not isinstance(raw.get("program"), str):
        raise AgentConfigError('each rule needs a "program" string')
    subcommands = raw.get("subcommands", [])
    if not isinstance(subcommands, list) or not all(isinstance(s, str) for s in subcommands):
        raise AgentConfigError('"subcommands" must be a list of strings')
    return CommandRule(raw["program"], tuple(subcommands), bool(raw.get("trust_unsandboxed", False)))


def parse_config(data: Any) -> AgentConfig:
    if not isinstance(data, dict):
        raise AgentConfigError("the file must contain a JSON object")
    commands = data.get("commands", {})
    if not isinstance(commands, dict):
        raise AgentConfigError('"commands" must be an object')
    rules = CommandRules(
        allow=tuple(parse_rule(r) for r in commands.get("allow", [])),
        deny=tuple(parse_rule(r) for r in commands.get("deny", [])),
    )
    return AgentConfig(rules)


def load_agent_config(root: str, io: Any) -> AgentConfig:
    path = Path(root) / CONFIG_FILE_NAME
    if not path.is_file():
        return AgentConfig()
    try:
        return parse_config(json.loads(path.read_text(encoding=CONFIG_ENCODING)))
    except (OSError, ValueError) as err:
        io.tool_warning(f"Ignoring {CONFIG_FILE_NAME}: {err}")
        return AgentConfig()


def instruction_files(root: str) -> list[str]:
    """Existing instruction files in the root, small enough to add to the chat."""
    found = []
    for name in INSTRUCTION_FILE_NAMES:
        path = Path(root) / name
        if path.is_file() and path.stat().st_size <= MAX_INSTRUCTION_BYTES:
            found.append(str(path))
    return found
