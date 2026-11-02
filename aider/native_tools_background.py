"""Background command tools: start a long-running command, read its new output, stop it.
Starting goes through the same command policy, approval and sandbox wrapper as run_command; output is written to a
temporary log file that read_background returns incrementally, so dev servers and watchers can be checked on.
At most MAX_BACKGROUND processes run at once, each in its own process group, and all are stopped when Aider exits;
a process that exits on its own is reported once (exit_notices), so the model learns of it without polling.
"""

import atexit
import os
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import IO

from aider.native_root_cd import without_root_cd
from aider.native_tool_context import ToolContext
from aider.native_toolcalling import NativeToolError, NativeToolRegistry
from aider.native_tools_shell import authorize, output_tail

MAX_BACKGROUND = 4
LOG_PREFIX = "aider-bg-"
ID_FORMAT = "bg{number}"
EXIT_NOTICE = "{id} ({command}) exited with code {code}; read_background {id} shows its last output."
STOP_TIMEOUT_SECONDS = 5

START_PARAMETERS = {
    "type": "object",
    "properties": {"command": {"type": "string", "description": "Long-running shell command to start."}},
    "required": ["command"],
}
ID_PARAMETERS = {
    "type": "object",
    "properties": {"id": {"type": "string", "description": "Id returned by start_background."}},
    "required": ["id"],
}


class BackgroundError(NativeToolError):
    """Raised for unknown ids or when too many background processes are running."""


@dataclass
class BackgroundProcess:
    command: str
    process: subprocess.Popen
    log: IO[bytes]
    read_offset: int = 0


class ProcessManager:
    """Background processes of one session."""

    def __init__(self) -> None:
        self.processes: dict[str, BackgroundProcess] = {}
        self.started = 0
        self.reported: set[str] = set()
        atexit.register(self.stop_all)

    def running(self) -> int:
        return sum(1 for p in self.processes.values() if p.process.poll() is None)

    def start(self, argv: list[str], cwd: Path, command: str) -> str:
        if self.running() >= MAX_BACKGROUND:
            raise BackgroundError(f"At most {MAX_BACKGROUND} background processes; stop one first")
        log = tempfile.NamedTemporaryFile(prefix=LOG_PREFIX, delete=False)
        process = subprocess.Popen(
            argv, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True
        )
        self.started += 1
        process_id = ID_FORMAT.format(number=self.started)
        self.processes[process_id] = BackgroundProcess(command, process, log)
        return process_id

    def get(self, process_id: str) -> BackgroundProcess:
        if process_id not in self.processes:
            raise BackgroundError(f"Unknown background id {process_id!r}; known: {sorted(self.processes)}")
        return self.processes[process_id]

    def read(self, process_id: str) -> str:
        entry = self.get(process_id)
        data = Path(entry.log.name).read_bytes()
        new, entry.read_offset = data[entry.read_offset :], len(data)
        code = entry.process.poll()
        state = "running" if code is None else f"exited with code {code}"
        return f"{process_id} ({entry.command}): {state}\n{output_tail(new.decode(errors='replace'))}"

    def exit_notices(self) -> list[str]:
        """One line for each process that exited since the last call, without being stopped by the agent."""
        notices = []
        for process_id, entry in self.processes.items():
            code = entry.process.poll()
            if code is not None and process_id not in self.reported:
                self.reported.add(process_id)
                notices.append(EXIT_NOTICE.format(id=process_id, command=entry.command, code=code))
        return notices

    def stop(self, process_id: str) -> str:
        entry = self.get(process_id)
        self.reported.add(process_id)
        if entry.process.poll() is None:
            os.killpg(entry.process.pid, signal.SIGTERM)
            try:
                entry.process.wait(STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                os.killpg(entry.process.pid, signal.SIGKILL)
        return self.read(process_id)

    def stop_all(self) -> None:
        for process_id, entry in list(self.processes.items()):
            if entry.process.poll() is None:
                self.stop(process_id)
            entry.log.close()
            Path(entry.log.name).unlink(missing_ok=True)


def start_background(ctx: ToolContext, manager: ProcessManager, command: str) -> str:
    command = without_root_cd(command, ctx.root)
    refusal = authorize(ctx, command)
    if refusal:
        return refusal
    process_id = manager.start(ctx.wrap_command(command), ctx.root, command)
    return f"Started {process_id}. Use read_background to see its output and stop_background to end it."


def register_background_tools(registry: NativeToolRegistry, ctx: ToolContext, manager: ProcessManager) -> None:
    """Add start_background, read_background and stop_background to `registry`."""
    registry.register(
        "start_background",
        "Start a long-running command (dev server, watcher) in the background; same approval as run_command.",
        START_PARAMETERS,
        lambda command: start_background(ctx, manager, command),
    )
    registry.register(
        "read_background", "Read new output and the status of a background command.", ID_PARAMETERS,
        lambda id: manager.read(id),
    )
    registry.register(
        "stop_background", "Stop a background command and return its last output.", ID_PARAMETERS,
        lambda id: manager.stop(id),
    )
