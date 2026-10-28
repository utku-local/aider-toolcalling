"""Offers to remember an approved command as a project allow rule ("always allow this").
After the user approves a plain, risk-free command, a second explicit question asks whether to add the narrowest
matching rule to .aider-agent.json; --yes-always never answers it, so rules are only added on purpose.
Outside the sandbox the rule is written as trusted, since the user is choosing to skip the question there too.
"""

from pathlib import Path
from typing import Any

from aider.native_command_policy import CommandRule, PolicyAction, decide, rule_for_command

from .native_agent_config import add_allow_rule


def describe_rule(rule: CommandRule) -> str:
    return " ".join([rule.program, *rule.subcommands])


def offer_allow_rule(coder: Any, command: str) -> None:
    """Ask whether to always allow `command`'s program; add the rule to the project config when confirmed."""
    root = Path(coder.root).resolve()
    rule = rule_for_command(command, root, trust_unsandboxed=not coder.native_sandboxed)
    if rule is None:
        return
    if decide(command, root, coder.native_agent_config.rules, coder.native_sandboxed).action is PolicyAction.ALLOW:
        return
    where = "" if coder.native_sandboxed else ", also outside the sandbox"
    question = f"Always allow `{describe_rule(rule)}` in this project without asking{where}?"
    if coder.io.confirm_ask(question, default="n", explicit_yes_required=True):
        coder.native_agent_config = add_allow_rule(coder.root, coder.native_agent_config, rule)
        coder.io.tool_output(f"Added an allow rule for `{describe_rule(rule)}` to .aider-agent.json")
