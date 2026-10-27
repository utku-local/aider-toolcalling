"""Per-request snapshots of files the agent changes, so /undo-agent can restore them without git.
Before the first change to a file in a request, its original bytes (or the fact that it did not exist) are kept;
undo writes the originals back and deletes files the request created, newest request first.
This covers edits that auto-commit would not, such as runs with --no-auto-commits.
"""

from pathlib import Path
from typing import Optional

MAX_SNAPSHOT_REQUESTS = 20


class SnapshotStore:
    """Originals per request: request number -> {absolute path: bytes, or None when the file was created}."""

    def __init__(self) -> None:
        self.requests: dict[int, dict[str, Optional[bytes]]] = {}

    def capture(self, request: int, path: str) -> None:
        originals = self.requests.setdefault(request, {})
        if path in originals:
            return
        target = Path(path)
        originals[path] = target.read_bytes() if target.is_file() else None
        for old in sorted(self.requests)[:-MAX_SNAPSHOT_REQUESTS]:
            del self.requests[old]

    def undo_latest(self) -> list[str]:
        """Restore the newest request with changes; returns the paths restored or removed."""
        if not self.requests:
            return []
        originals = self.requests.pop(max(self.requests))
        for path, content in originals.items():
            target = Path(path)
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.write_bytes(content)
        return sorted(originals)
