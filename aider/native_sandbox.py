"""macOS sandbox for agent commands: writes only inside the project and temp directories, no network.
The profile is built here as text for sandbox-exec; reads stay allowed so compilers and interpreters work, while
file writes elsewhere and every network connection except local unix sockets are denied by the kernel.
When sandbox-exec is not available, commands run through a plain /bin/sh and the policy treats them as unsandboxed.
"""

import shutil
from pathlib import Path

SANDBOX_EXEC = "sandbox-exec"
SHELL = "/bin/sh"
SHELL_FLAG = "-c"
WRITABLE_SYSTEM_PATHS = ("/private/tmp", "/private/var/folders", "/dev")


def quote(path: str) -> str:
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"') + '"'


def sandbox_profile(root: Path) -> str:
    """Seatbelt profile: everything allowed except writes outside `root` and temp dirs, and network access."""
    writable = [str(root.resolve())] + list(WRITABLE_SYSTEM_PATHS)
    subpaths = " ".join(f"(subpath {quote(path)})" for path in writable)
    return (
        "(version 1)(allow default)"
        "(deny network*)(allow network* (remote unix-socket))"
        f"(deny file-write*)(allow file-write* {subpaths})"
    )


def sandbox_available() -> bool:
    return shutil.which(SANDBOX_EXEC) is not None


def shell_argv(command: str) -> list[str]:
    return [SHELL, SHELL_FLAG, command]


def sandboxed_argv(root: Path, command: str) -> list[str]:
    return [SANDBOX_EXEC, "-p", sandbox_profile(root), *shell_argv(command)]
