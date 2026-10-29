"""Built-in read-only tools exposed to the model when --native-tools is enabled.
It registers read_file and list_files on a NativeToolRegistry, and both resolve every path inside one root.
This is the filesystem adapter of the tool loop; paths that escape the root raise ToolPathError.
"""

from pathlib import Path
from typing import Optional

from aider.native_sensitive import is_sensitive
from aider.native_documents import document_text
from aider.native_tool_context import DENIED_ACTION, ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolError, NativeToolRegistry

MAX_READ_CHARS = 100_000
# Without a line range, read_file returns at most this many lines of a larger file.
DEFAULT_MAX_LINES = 120
PARTIAL_NOTE = (
    "\n[showing lines 1-{shown} of {total}; use search_code to find the part you need, "
    "then read_file with start_line and end_line]"
)
MAX_LIST_ENTRIES = 500
TRUNCATED_NOTE = "\n[truncated]"
DEFAULT_LIST_PATH = "."
DIR_SUFFIX = "/"
FILE_ENCODING = "utf-8"

READ_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path relative to the project root."},
        "start_line": {
            "type": "integer",
            "description": "First line to return (1-based, inclusive). Defaults to the first line.",
        },
        "end_line": {
            "type": "integer",
            "description": "Last line to return (1-based, inclusive). Defaults to the last line.",
        },
    },
    "required": ["path"],
}
LIST_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {
            "type": "string",
            "description": "Directory relative to the project root. Defaults to the root.",
        },
    },
}


class ToolPathError(NativeToolError):
    """Raised when a tool path is outside the root or of the wrong kind."""


def resolve_in_root(root: Path, path: str) -> Path:
    target = (root / path).resolve()
    if target != root and root not in target.parents:
        raise ToolPathError(f"Path is outside the project root: {path!r}")
    return target


def select_lines(text: str, start_line: Optional[int], end_line: Optional[int]) -> str:
    """Lines start_line..end_line (1-based, inclusive); the whole text when both are None."""
    if start_line is None and end_line is None:
        return text
    lines = text.splitlines(keepends=True)
    first = max(start_line or 1, 1)
    last = min(end_line or len(lines), len(lines))
    if first > last:
        raise ToolPathError(f"Line range {first}-{last} is empty; the file has {len(lines)} lines")
    return "".join(lines[first - 1 : last])


def read_file(
    root: Path, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None
) -> str:
    target = resolve_in_root(root, path)
    if not target.is_file():
        raise ToolPathError(f"Not a file: {path!r}")
    document = document_text(target, path)
    full = document if document is not None else target.read_text(encoding=FILE_ENCODING, errors="replace")
    total_lines = len(full.splitlines())
    if start_line is None and end_line is None and total_lines > DEFAULT_MAX_LINES:
        # Whole large files flood every later prompt; return the start and say how to read on.
        shown = select_lines(full, 1, DEFAULT_MAX_LINES)
        return shown + PARTIAL_NOTE.format(shown=DEFAULT_MAX_LINES, total=total_lines)
    text = select_lines(full, start_line, end_line)
    if len(text) > MAX_READ_CHARS:
        return text[:MAX_READ_CHARS] + TRUNCATED_NOTE
    return text


def list_files(root: Path, path: str = DEFAULT_LIST_PATH) -> str:
    target = resolve_in_root(root, path)
    if not target.is_dir():
        raise ToolPathError(f"Not a directory: {path!r}")
    names = sorted(
        entry.name + (DIR_SUFFIX if entry.is_dir() else "") for entry in target.iterdir()
    )
    listing = "\n".join(names[:MAX_LIST_ENTRIES])
    if len(names) > MAX_LIST_ENTRIES:
        listing += TRUNCATED_NOTE
    return listing


def guarded_read(
    ctx: ToolContext, path: str, start_line: Optional[int] = None, end_line: Optional[int] = None
) -> str:
    """read_file that asks before reading a file that usually holds secrets."""
    if is_sensitive(path) and not ctx.approve(
        ToolPermission.SENSITIVE, f"Read {path}? It may contain secrets.", path
    ):
        return DENIED_ACTION
    text = read_file(ctx.root, path, start_line, end_line)
    if ctx.file_state is not None:
        ctx.file_state.record(resolve_in_root(ctx.root, path))
    return text


def register_read_tools(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add read_file and list_files, bound to `ctx`, to `registry`."""
    registry.register(
        "read_file",
        "Read a file from the project, optionally only a range of lines. Notebooks (.ipynb) come back as cells "
        "with outputs and PDFs as text.",
        READ_PARAMETERS,
        lambda path, start_line=None, end_line=None: guarded_read(ctx, path, start_line, end_line),
    )
    registry.register(
        "list_files",
        "List the entries of a project directory; directories end with '/'.",
        LIST_PARAMETERS,
        lambda path=DEFAULT_LIST_PATH: list_files(ctx.root, path),
    )


def never_approve(permission: ToolPermission, title: str, details: str) -> bool:
    return False


def build_builtin_registry(root: str) -> NativeToolRegistry:
    """Registry with the read-only tools bound to `root`; reading secret files is always declined."""
    ctx = ToolContext(
        root=Path(root).resolve(), list_files=list, find_tags=lambda abs_path, rel_path: [],
        approve=never_approve, on_edit=lambda path: None, dry_run=False,
    )
    registry = NativeToolRegistry()
    register_read_tools(registry, ctx)
    return registry
