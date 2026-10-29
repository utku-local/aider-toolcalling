"""Tells the model what its command environment allows, up front and next to the errors it causes.
The system prompt gets a short note on the sandbox (writes, network, localhost) and on missing services, and
command output that shows a refused connection or a sandbox denial gets a one-line explanation appended.
In a trial session the model spent half an hour on connection errors caused by the sandbox and a service that was
not running, because nothing told it either; these notes name the cause so it can report it to the user instead.
"""

SANDBOX_NOTE = """Commands run in a macOS sandbox: they can write only inside the project and temp directories, and
they can reach only localhost; the internet is blocked. A local service (database, download daemon, API server) is
reachable only if it is already running on this machine."""
UNSANDBOXED_NOTE = """Commands run directly on the user's machine, without a sandbox."""
SERVICES_NOTE = """Before you debug a connection error, check that the service is running (for example
`lsof -nP -iTCP -sTCP:LISTEN` or `pgrep -fl <name>`). If a service the project needs is not running, or the
environment blocks something the task needs, stop and tell the user what is missing and the exact command to start
or allow it; do not work around it in the code. If the same kind of error comes back several times, stop, summarize
what you tried, and ask the user how to proceed."""

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


def environment_note(sandboxed: bool) -> str:
    """The system-prompt section describing where commands run and what to do when something is missing."""
    return f"{SANDBOX_NOTE if sandboxed else UNSANDBOXED_NOTE}\n{SERVICES_NOTE}\n"


def command_hint(output: str, sandboxed: bool) -> str:
    """One explanatory line for a refused connection or a sandbox denial in `output`; empty when neither applies."""
    if any(marker in output for marker in REFUSED_MARKERS):
        return REFUSED_HINT
    if sandboxed and any(marker in output for marker in SANDBOX_DENIED_MARKERS):
        return SANDBOX_HINT
    return ""
