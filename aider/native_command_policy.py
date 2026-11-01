"""Command policy for run_command: parses a shell command into argv and decides ALLOW, ASK or DENY.
Decisions use the parsed program, subcommand and arguments: compound commands (lists, redirects, substitutions,
env prefixes, pipes into anything but a read-only filter) are never auto-allowed, path arguments outside the project
are flagged, and network, deletion, remote git, package installs and privilege escalation are separate risks.
Redirects to /dev/null and pipes into filters such as head or grep add no risk, so they do not trigger a prompt.
Allow rules auto-approve only inside a sandbox unless a rule explicitly trusts unsandboxed runs.
"""

import re
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
SUBCOMMAND_PROGRAMS = frozenset({"git", "npm", "yarn", "pnpm", "uv", "pip", "pip3", "cargo", "go", "docker", "brew"})


STDERR_MERGE = "2>&1"
NULL_DEVICE = "/dev/null"
PIPE = "|"
# Redirects that only discard or merge output; removed before the command is judged (it still runs unchanged).
# Measured: `2>/dev/null` was flagged as a compound command and a path outside the project on every call.
HARMLESS_REDIRECT = re.compile(r"(?<!\S)(?:[12]?>|&>)\s*/dev/null(?=\s|$|[|;&])|(?<!\S)2>&1(?=\s|$|[|;&])")
# Programs that only read their input and print; a pipe into them adds no risk.
READ_ONLY_FILTERS = frozenset(
    {"head", "tail", "grep", "egrep", "fgrep", "rg", "wc", "cut", "uniq", "sort", "tr", "jq", "nl", "column"}
)
# Filter flags that write a file or run a program.
UNSAFE_FILTER_FLAGS = {"sort": ("-o", "--output"), "rg": ("--pre",)}


def without_stderr_merge(command: str) -> str:
    """Drop a trailing `2>&1`: run_command already returns stdout and stderr together, so it changes nothing."""
    stripped = command.rstrip()
    if stripped.endswith(STDERR_MERGE):
        return stripped[: -len(STDERR_MERGE)].rstrip()
    return command


def tokenize(command: str) -> Optional[list[str]]:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        return list(lexer)
    except ValueError:
        return None


def without_harmless_redirects(command: str) -> str:
    """`command` without redirects to /dev/null and `2>&1`; used only to judge the command, never to run it."""
    return HARMLESS_REDIRECT.sub(" ", command).strip()


def pipeline_stages(tokens: list[str]) -> list[list[str]]:
    """The argv of each stage of a plain pipeline; a single stage when there is no pipe."""
    stages: list[list[str]] = [[]]
    for token in tokens:
        if token == PIPE:
            stages.append([])
        else:
            stages[-1].append(token)
    return stages


def is_read_only_filter(argv: list[str]) -> bool:
    if not argv:
        return False
    program = PurePosixPath(argv[0]).name
    unsafe = UNSAFE_FILTER_FLAGS.get(program, ())
    return program in READ_ONLY_FILTERS and not any(arg.startswith(unsafe) for arg in argv[1:] if unsafe)


def is_compound(command: str, tokens: list[str]) -> bool:
    """True for anything but one plain command, optionally piped into read-only filters."""
    stages = pipeline_stages(tokens)
    operators = any(token and set(token) <= OPERATOR_CHARS for stage in stages for token in stage)
    filters_only = all(is_read_only_filter(stage) for stage in stages[1:])
    env_prefix = bool(tokens) and "=" in tokens[0] and not tokens[0].startswith("-")
    return operators or not filters_only or not stages[0] or env_prefix or bool(EXPANSION_CHARS & set(command)) \
        or "\n" in command


def program_and_args(argv: list[str]) -> tuple[str, list[str]]:
    """`python -m pytest -q` -> ("pytest", ["-q"]); otherwise the basename of argv[0]."""
    program = PurePosixPath(argv[0]).name
    if program in PYTHON_PROGRAMS and len(argv) > 2 and argv[1] == "-m":
        return argv[2], argv[3:]
    return program, argv[1:]


def outside_root(args: list[str], root: Path) -> bool:
    for arg in args:
        value = arg.split("=", 1)[1] if arg.startswith("-") and "=" in arg else arg
        if value.startswith("-") or not value or value == NULL_DEVICE:
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


def rule_for_command(command: str, root: Path, trust_unsandboxed: bool) -> Optional[CommandRule]:
    """The narrowest allow rule covering a plain, risk-free command; None for anything else.

    Programs whose first argument selects an action (git, npm, uv, ...) get a rule for that subcommand only.
    """
    tokens = tokenize(command)
    if not tokens or is_compound(command, tokens) or PIPE in tokens:
        return None
    program, args = program_and_args(tokens)
    if risks_of(program, args, root) or denial(program, args, set()):
        return None
    subcommands = (args[0],) if program in SUBCOMMAND_PROGRAMS and args and not args[0].startswith("-") else ()
    if program in SUBCOMMAND_PROGRAMS and not subcommands:
        return None
    return CommandRule(program, subcommands, trust_unsandboxed)


def decide(command: str, root: Path, rules: CommandRules, sandboxed: bool) -> PolicyDecision:
    """The policy decision for one run_command call; rules match the first stage of a pipeline."""
    command = without_harmless_redirects(command)
    tokens = tokenize(command)
    if not tokens or not tokens[0] or tokens[0] == PIPE:
        return PolicyDecision(PolicyAction.ASK, frozenset({Risk.UNPARSEABLE}))
    stages = pipeline_stages(tokens)
    if is_compound(command, tokens):
        program, args = program_and_args(tokens)
        risks = risks_of(program, args, root) | {Risk.COMPOUND}
    else:
        program, args = program_and_args(stages[0])
        risks = set().union(*(risks_of(*program_and_args(stage), root) for stage in stages))
    reason = denial(program, args, risks)
    if reason:
        return PolicyDecision(PolicyAction.DENY, frozenset(risks), reason)
    if any(matches(rule, program, args) for rule in rules.deny):
        return PolicyDecision(PolicyAction.DENY, frozenset(risks), f"{program} is denied by the project rules")
    allowed = [rule for rule in rules.allow if matches(rule, program, args)]
    if allowed and not risks and (sandboxed or any(rule.trust_unsandboxed for rule in allowed)):
        return PolicyDecision(PolicyAction.ALLOW)
    return PolicyDecision(PolicyAction.ASK, frozenset(risks))
