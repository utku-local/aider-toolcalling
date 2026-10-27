"""Built-in read-only tools exposed to the model when --native-tools is enabled.
It registers read_file and list_files on a NativeToolRegistry, and both resolve every path inside one root.
This is the filesystem adapter of the tool loop; paths that escape the root raise ToolPathError.
"""

from pathlib import Path

from aider.native_toolcalling import NativeToolError, NativeToolRegistry

MAX_READ_CHARS = 100_000
MAX_LIST_ENTRIES = 500
TRUNCATED_NOTE = "\n[truncated]"
DEFAULT_LIST_PATH = "."
DIR_SUFFIX = "/"
FILE_ENCODING = "utf-8"

PATH_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path relative to the project root."},
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


def read_file(root: Path, path: str) -> str:
    target = resolve_in_root(root, path)
    if not target.is_file():
        raise ToolPathError(f"Not a file: {path!r}")
    text = target.read_text(encoding=FILE_ENCODING, errors="replace")
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


def build_builtin_registry(root: str) -> NativeToolRegistry:
    """Registry with the read-only tools bound to the given project root."""
    root_path = Path(root).resolve()
    registry = NativeToolRegistry()
    registry.register(
        "read_file",
        "Read a text file from the project.",
        PATH_PARAMETERS,
        lambda path: read_file(root_path, path),
    )
    registry.register(
        "list_files",
        "List the entries of a project directory; directories end with '/'.",
        LIST_PARAMETERS,
        lambda path=DEFAULT_LIST_PATH: list_files(root_path, path),
    )
    return registry
