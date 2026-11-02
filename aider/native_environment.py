"""Tells the model what its command environment allows, up front and next to the errors it causes.
The system prompt gets the working directory, the OS and the project's Python runner, a short note on the sandbox
(writes, network, localhost) and on missing services; command output that shows a refused connection, a sandbox
denial or a grep without matches gets a one-line explanation appended.
In a trial session the model spent half an hour on connection errors caused by the sandbox and a service that was
not running, because nothing told it either; these notes name the cause so it can report it to the user instead.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Optional

SANDBOX_NOTE = """Commands run in a macOS sandbox: they can write only inside the project and temp directories, and
they can reach only localhost; the internet is blocked. A local service (database, download daemon, API server) is
reachable only if it is already running on this machine."""
UNSANDBOXED_NOTE = """Commands run directly on the user's machine, without a sandbox."""
SERVICES_NOTE = """Before you debug a connection error, check that the service is running (for example
`lsof -nP -iTCP -sTCP:LISTEN` or `pgrep -fl <name>`). If a service the project needs is not running, or the
environment blocks something the task needs, stop and tell the user what is missing and the exact command to start
or allow it; do not work around it in the code. If the same kind of error comes back several times, stop, summarize
what you tried, and ask the user how to proceed."""

# Measured: without them a model ran `cd /home/user` and checked the system pip, which lacks the project's packages.
WORKDIR_NOTE = "Working directory: {root} ({os_name}). Commands already run here; use paths relative to it."
PYTHON_NOTE = "Python: run the project's code and tools with `{runner}`, not a bare python3 or pip."
NO_PYTHON_NOTE = "No project virtualenv was found; ask the user which Python to use before installing anything."
# (marker file in the project root, how to run Python there), first match wins.
PYTHON_RUNNERS = (
    ("uv.lock", "uv run python"),
    ("poetry.lock", "poetry run python"),
    (".venv/bin/python", ".venv/bin/python"),
    ("venv/bin/python", "venv/bin/python"),
)
PYTHON_PROJECT_MARKERS = ("pyproject.toml", "setup.py", "requirements.txt")
OS_NAMES = {"Darwin": "macOS"}
SEARCH_PROGRAMS = frozenset({"grep", "egrep", "fgrep", "rg"})
NO_MATCH_EXIT = 1
NO_MATCH_HINT = "Note: grep and rg exit 1 when nothing matched; this is a result (no matches), not an error."


@dataclass(frozen=True)
class EnvironmentFacts:
    """What the model needs to know about where it runs; `python_runner` None means none was found."""

    root: str
    os_name: str
    python_project: bool = False
    python_runner: Optional[str] = None


REFUSED_MARKERS = ("Connection refused", "[Errno 61]", "ECONNREFUSED")
SANDBOX_DENIED_MARKERS = ("Operation not permitted", "[Errno 1]", "EPERM")
REFUSED_HINT = (
    "Note: the connection was refused, so nothing is listening on that port. The service is probably not running; "
    "check with `lsof -nP -iTCP -sTCP:LISTEN`, and if the project needs it, tell the user how to start it."
)
SANDBOX_HINT = (
    "Note: the sandbox likely blocked this (internet access, or a write outside the project). It is not a bug in "
    "the code; if the task needs it, tell the user."
)


def python_runner(files: frozenset[str]) -> Optional[str]:
    """How to run Python in a project whose root holds `files` (relative paths that exist); None when unknown."""
    return next((runner for marker, runner in PYTHON_RUNNERS if marker in files), None)


def detect_environment(root: Path, system: str) -> EnvironmentFacts:
    """The facts for `root` on `system` (platform.system()); the only I/O is checking which marker files exist."""
    markers = {marker for marker, _ in PYTHON_RUNNERS} | set(PYTHON_PROJECT_MARKERS)
    present = frozenset(marker for marker in markers if (root / marker).exists())
    return EnvironmentFacts(
        root=str(root),
        os_name=OS_NAMES.get(system, system),
        python_project=bool(present),
        python_runner=python_runner(present),
    )


def location_note(facts: EnvironmentFacts) -> str:
    lines = [WORKDIR_NOTE.format(root=facts.root, os_name=facts.os_name)]
    if facts.python_runner:
        lines.append(PYTHON_NOTE.format(runner=facts.python_runner))
    elif facts.python_project:
        lines.append(NO_PYTHON_NOTE)
    return "\n".join(lines)


def environment_note(sandboxed: bool, facts: Optional[EnvironmentFacts] = None) -> str:
    """The system-prompt section describing where commands run and what to do when something is missing."""
    location = f"{location_note(facts)}\n" if facts is not None else ""
    return f"{location}{SANDBOX_NOTE if sandboxed else UNSANDBOXED_NOTE}\n{SERVICES_NOTE}\n"


def last_program(command: str) -> str:
    """The program of the last pipeline stage, by a plain split; good enough for a hint."""
    words = command.rsplit("|", 1)[-1].split()
    return PurePosixPath(words[0]).name if words else ""


def no_match_hint(command: str, exit_code: int, output: str) -> str:
    """The grep/rg "exit 1 means no matches" note; empty when it does not apply."""
    if exit_code == NO_MATCH_EXIT and not output.strip() and last_program(command) in SEARCH_PROGRAMS:
        return NO_MATCH_HINT
    return ""


def command_hint(output: str, sandboxed: bool) -> str:
    """One explanatory line for a refused connection or a sandbox denial in `output`; empty when neither applies."""
    if any(marker in output for marker in REFUSED_MARKERS):
        return REFUSED_HINT
    if sandboxed and any(marker in output for marker in SANDBOX_DENIED_MARKERS):
        return SANDBOX_HINT
    return ""
