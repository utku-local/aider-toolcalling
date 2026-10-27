"""Command policy for run_command: parses a shell command into argv and decides ALLOW, ASK or DENY.
Decisions use the parsed program, subcommand and arguments, never a text pattern: compound commands (pipes, lists,
redirects, substitutions, env prefixes) are never auto-allowed, path arguments outside the project are flagged, and
network, deletion, remote git, package installs and privilege escalation are separate risks.
Allow rules auto-approve only inside a sandbox unless a rule explicitly trusts unsandboxed runs.
"""

import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Optional


class PolicyAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class Risk(str, Enum):
    COMPOUND = "compound command (pipe, list, redirect, substitution or env prefix)"
    UNPARSEABLE = "command could not be parsed"
    OUTSIDE_ROOT = "path argument outside the project"
    NETWORK = "network access"
    DELETE = "deletes files"
    GIT_REMOTE = "talks to a git remote"
    PACKAGE_INSTALL = "installs packages"
    PRIVILEGE = "privilege escalation"


@dataclass(frozen=True)
class CommandRule:
    """Matches a program and, optionally, its first argument; `trust_unsandboxed` allows it without a sandbox."""

    program: str
    subcommands: tuple[str, ...] = ()
    trust_unsandboxed: bool = False


@dataclass(frozen=True)
class CommandRules:
    allow: tuple[CommandRule, ...] = ()
    deny: tuple[CommandRule, ...] = ()


@dataclass(frozen=True)
class PolicyDecision:
    action: PolicyAction
    risks: frozenset[Risk] = field(default_factory=frozenset)
    reason: str = ""


OPERATOR_CHARS = frozenset("|&;<>()")
EXPANSION_CHARS = frozenset("$`")
PYTHON_PROGRAMS = frozenset({"python", "python3"})
NETWORK_PROGRAMS = frozenset({"curl", "wget", "ssh", "scp", "sftp", "rsync", "nc", "ncat", "telnet", "ftp"})
DELETE_PROGRAMS = frozenset({"rm", "rmdir", "unlink", "shred"})
PRIVILEGE_PROGRAMS = frozenset({"sudo", "su", "doas"})
GIT_REMOTE_SUBCOMMANDS = frozenset({"push", "pull", "fetch", "clone", "remote", "submodule"})
INSTALL_SUBCOMMANDS = {"pip": {"install", "download"}, "pip3": {"install", "download"}, "npm": {"install", "i", "ci"},
                       "yarn": {"add", "install"}, "uv": {"add", "pip", "sync"}, "brew": {"install"}}
FORCE_FLAGS = frozenset({"--force", "-f", "--force-with-lease"})
RECURSIVE_FLAGS = frozenset({"-r", "-R", "-rf", "-fr", "-Rf", "-fR", "--recursive"})
ROOT_TARGETS = frozenset({".", "./", "*"})


def tokenize(command: str) -> Optional[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return None


def is_compound(command: str, tokens: list[str]) -> bool:
    operators = any(token and set(token) <= OPERATOR_CHARS for token in tokens)
    env_prefix = bool(tokens) and "=" in tokens[0] and not tokens[0].startswith("-")
    return operators or env_prefix or bool(EXPANSION_CHARS & set(command)) or "\n" in command


def program_and_args(argv: list[str]) -> tuple[str, list[str]]:
    """`python -m pytest -q` -> ("pytest", ["-q"]); otherwise the basename of argv[0]."""
    program = PurePosixPath(argv[0]).name
    if program in PYTHON_PROGRAMS and len(argv) > 2 and argv[1] == "-m":
        return argv[2], argv[3:]
    return program, argv[1:]


def outside_root(args: list[str], root: Path) -> bool:
    for arg in args:
        value = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
        if value.startswith("-") or not value:
            continue
        if value.startswith(("/", "~", "..")) or "/.." in value:
            target = (root / Path(value).expanduser()).resolve()
            if target != root and root not in target.parents:
                return True
    return False


def risks_of(program: str, args: list[str], root: Path) -> set[Risk]:
    risks = set()
    subcommand = args[0] if args else ""
    if program in NETWORK_PROGRAMS:
        risks.add(Risk.NETWORK)
    if program in DELETE_PROGRAMS or (program == "git" and subcommand in {"clean", "rm"}):
        risks.add(Risk.DELETE)
    if program in PRIVILEGE_PROGRAMS:
        risks.add(Risk.PRIVILEGE)
    if program == "git" and subcommand in GIT_REMOTE_SUBCOMMANDS:
        risks |= {Risk.GIT_REMOTE, Risk.NETWORK}
    if subcommand in INSTALL_SUBCOMMANDS.get(program, set()):
        risks |= {Risk.PACKAGE_INSTALL, Risk.NETWORK}
    if outside_root(args, root):
        risks.add(Risk.OUTSIDE_ROOT)
    return risks


def denial(program: str, args: list[str], risks: set[Risk]) -> str:
    if Risk.PRIVILEGE in risks:
        return "privilege escalation is never run by the agent"
    if program == "git" and args[:1] == ["push"] and FORCE_FLAGS & set(args):
        return "force pushes are never run by the agent"
    if program == "rm" and RECURSIVE_FLAGS & set(args) and (Risk.OUTSIDE_ROOT in risks or ROOT_TARGETS & set(args)):
        return "recursive deletion of the project root or outside it is never run by the agent"
    return ""


def matches(rule: CommandRule, program: str, args: list[str]) -> bool:
    return rule.program == program and (not rule.subcommands or bool(args) and args[0] in rule.subcommands)


def decide(command: str, root: Path, rules: CommandRules, sandboxed: bool) -> PolicyDecision:
    """The policy decision for one run_command call."""
    tokens = tokenize(command)
    if not tokens:
        return PolicyDecision(PolicyAction.ASK, frozenset({Risk.UNPARSEABLE}))
    program, args = program_and_args(tokens)
    risks = risks_of(program, args, root)
    if is_compound(command, tokens):
        risks.add(Risk.COMPOUND)
    reason = denial(program, args, risks)
    if reason:
        return PolicyDecision(PolicyAction.DENY, frozenset(risks), reason)
    if any(matches(rule, program, args) for rule in rules.deny):
        return PolicyDecision(PolicyAction.DENY, frozenset(risks), f"{program} is denied by the project rules")
    allowed = [rule for rule in rules.allow if matches(rule, program, args)]
    if allowed and not risks and (sandboxed or any(rule.trust_unsandboxed for rule in allowed)):
        return PolicyDecision(PolicyAction.ALLOW)
    return PolicyDecision(PolicyAction.ASK, frozenset(risks))
