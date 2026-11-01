"""Tracks which project files the agent has read, so it never edits a file blind or from a stale copy.
A read or the agent's own write records the file's modification time and size; an edit of an existing file is
refused when the file was never read, or when it changed on disk since (another tool, an editor, the user).
New files can be written without a read, and the record is updated after every successful write.
"""

from pathlib import Path
from typing import Optional

from aider.native_toolcalling import NativeToolError

Stamp = tuple[int, int]
NOT_READ = "Read {path} before changing it, so the edit is based on its current content."
CHANGED = "{path} changed on disk since you last read it; read it again before changing it."


class StaleFileError(NativeToolError):
    """Raised when an edit would be based on a file the agent has not read, or an outdated copy of it."""


def stamp(path: Path) -> Optional[Stamp]:
    """Modification time and size of `path`, or None when it does not exist."""
    try:
        info = path.stat()
    except OSError:
        return None
    return info.st_mtime_ns, info.st_size


class FileState:
    """The stamps of the files the agent has read or written in this session."""

    def __init__(self) -> None:
        self.seen: dict[str, Stamp] = {}

    def record(self, path: Path) -> None:
        current = stamp(path)
        if current is not None:
            self.seen[str(path.resolve())] = current

    def unchanged(self, path: Path) -> bool:
        """True when `path` was read or written before and is the same on disk now."""
        known = self.seen.get(str(path.resolve()))
        return known is not None and known == stamp(path)

    def check_before_change(self, path: Path, shown: str) -> None:
        """Raise unless `path` is new, or was read and is unchanged since; `shown` names it in the message."""
        current = stamp(path)
        if current is None:
            return
        known = self.seen.get(str(path.resolve()))
        if known is None:
            raise StaleFileError(NOT_READ.format(path=shown))
        if known != current:
            raise StaleFileError(CHANGED.format(path=shown))
