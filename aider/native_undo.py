"""The /undo-agent command: restores the files the agent's tools changed in its most recent request.
It uses the per-request snapshots taken before each write, so it works without git and without auto-commits.
Created files are removed, changed files get their original bytes back, and each run undoes one more request.
"""

from pathlib import Path
from typing import Any

NOTHING_TO_UNDO = "The agent has no file changes left to undo in this session."


def undo_agent_request(coder: Any) -> None:
    snapshots = getattr(coder, "native_snapshots", None)
    restored = snapshots.undo_latest() if snapshots is not None else []
    if not restored:
        coder.io.tool_error(NOTHING_TO_UNDO)
        return
    for path in restored:
        state = "restored" if Path(path).exists() else "removed"
        coder.io.tool_output(f"Undo: {state} {coder.get_rel_fname(path)}")
