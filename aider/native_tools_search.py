"""Read-only search tools: find_files by glob, search_code by regex and find_symbol by definition name.
They work over the project file list from the ToolContext, so ignored and untracked noise stays out of results.
find_symbol uses Aider's tree-sitter tags, the same data that builds the repo map.
"""

import fnmatch
import re
from typing import Optional

from aider.native_tool_context import ToolContext
from aider.native_toolcalling import NativeToolError, NativeToolRegistry
from aider.native_tools_builtin import FILE_ENCODING, TRUNCATED_NOTE

MAX_FILE_RESULTS = 200
MAX_MATCHES = 200
MAX_MATCH_LINE_CHARS = 300
MAX_SEARCH_FILE_BYTES = 2_000_000
DEFINITION_KIND = "def"
NO_RESULTS = "No matches."

FIND_FILES_PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {
            "type": "string",
            "description": "Glob matched against project-relative paths, e.g. '*.py' or 'src/*/test_*'.",
        },
    },
    "required": ["pattern"],
}
SEARCH_CODE_PARAMETERS = {
    "type": "object",
    "properties": {
        "pattern": {"type": "string", "description": "Python regular expression to search for."},
        "file_glob": {
            "type": "string",
            "description": "Only search files whose path matches this glob. Defaults to all files.",
        },
        "ignore_case": {"type": "boolean", "description": "Case-insensitive search."},
    },
    "required": ["pattern"],
}
FIND_SYMBOL_PARAMETERS = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Exact name of a function, class or method."},
    },
    "required": ["name"],
}


class SearchError(NativeToolError):
    """Raised for invalid search input, such as a malformed regular expression."""


def limited(lines: list[str], limit: int) -> str:
    if not lines:
        return NO_RESULTS
    text = "\n".join(lines[:limit])
    return text + TRUNCATED_NOTE if len(lines) > limit else text


def find_files(ctx: ToolContext, pattern: str) -> str:
    return limited([p for p in ctx.list_files() if fnmatch.fnmatch(p, pattern)], MAX_FILE_RESULTS)


def file_lines(ctx: ToolContext, rel_path: str) -> list[str]:
    path = ctx.root / rel_path
    try:
        if not path.is_file() or path.stat().st_size > MAX_SEARCH_FILE_BYTES:
            return []
        return path.read_text(encoding=FILE_ENCODING, errors="replace").splitlines()
    except OSError:
        return []


def search_code(
    ctx: ToolContext, pattern: str, file_glob: Optional[str] = None, ignore_case: bool = False
) -> str:
    try:
        regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    except re.error as err:
        raise SearchError(f"Invalid regular expression {pattern!r}: {err}") from err
    matches = []
    for rel_path in ctx.list_files():
        if file_glob and not fnmatch.fnmatch(rel_path, file_glob):
            continue
        for number, line in enumerate(file_lines(ctx, rel_path), start=1):
            if regex.search(line):
                matches.append(f"{rel_path}:{number}: {line.strip()[:MAX_MATCH_LINE_CHARS]}")
            if len(matches) > MAX_MATCHES:
                return limited(matches, MAX_MATCHES)
    return limited(matches, MAX_MATCHES)


def find_symbol(ctx: ToolContext, name: str) -> str:
    found = []
    for rel_path in ctx.list_files():
        for tag in ctx.find_tags(str(ctx.root / rel_path), rel_path):
            if tag.kind == DEFINITION_KIND and tag.name == name:
                found.append(f"{rel_path}:{tag.line + 1}: {name}")
    return limited(found, MAX_MATCHES)


def register_search_tools(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add find_files, search_code and find_symbol, bound to `ctx`, to `registry`."""
    registry.register(
        "find_files",
        "Find project files whose relative path matches a glob.",
        FIND_FILES_PARAMETERS,
        lambda pattern: find_files(ctx, pattern),
    )
    registry.register(
        "search_code",
        "Search project files for a regular expression; returns path:line: text matches.",
        SEARCH_CODE_PARAMETERS,
        lambda pattern, file_glob=None, ignore_case=False: search_code(
            ctx, pattern, file_glob, ignore_case
        ),
    )
    registry.register(
        "find_symbol",
        "Find where a function, class or method is defined; returns path:line matches.",
        FIND_SYMBOL_PARAMETERS,
        lambda name: find_symbol(ctx, name),
    )
