"""Shared context handed to native tools: project root, file listing, approval and edit tracking.
Tools receive callables instead of Aider's io or Coder objects, so each tool module stays a thin adapter
that can be tested with plain functions.
ToolPermission names the approval level a tool needs before it may act.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class ToolPermission(str, Enum):
    """READ runs without asking; WRITE and EXECUTE need the user's approval."""

    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


@dataclass(frozen=True)
class ToolContext:
    """Everything a tool may touch. `approve(permission, title, details)` returns True to proceed."""

    root: Path
    list_files: Callable[[], list[str]]
    find_tags: Callable[[str, str], list[Any]]
    approve: Callable[[ToolPermission, str, str], bool]
    on_edit: Callable[[str], None]
    dry_run: bool
