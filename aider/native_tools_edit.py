"""File-changing tools: edit_file replaces an exact string, write_file creates or overwrites a file.
Every change is shown to the user as a unified diff and needs WRITE approval through the ToolContext.
Approved changes are reported through ctx.on_edit so Aider can lint, commit and test them like its own edits.
"""

import difflib
from pathlib import Path

from aider.native_tool_context import ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolError, NativeToolRegistry
from aider.native_tools_builtin import FILE_ENCODING, resolve_in_root

MAX_DIFF_LINES = 200
DIFF_TRUNCATED = "... (diff truncated)"
DENIED_MESSAGE = "The user declined this change. Ask them how to proceed or try a different approach."
DRY_RUN_NOTE = " (dry run: nothing was written)"

EDIT_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path relative to the project root."},
        "old_string": {
            "type": "string",
            "description": "Exact text to replace, including indentation. Must occur exactly once "
            "unless replace_all is true.",
        },
        "new_string": {"type": "string", "description": "Replacement text."},
        "replace_all": {"type": "boolean", "description": "Replace every occurrence."},
    },
    "required": ["path", "old_string", "new_string"],
}
WRITE_PARAMETERS = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path relative to the project root."},
        "content": {"type": "string", "description": "Complete new content of the file."},
    },
    "required": ["path", "content"],
}


class EditError(NativeToolError):
    """Raised when an edit cannot be applied as requested."""


def make_diff(rel_path: str, before: str, after: str) -> str:
    lines = list(
        difflib.unified_diff(
            before.splitlines(), after.splitlines(), f"a/{rel_path}", f"b/{rel_path}", lineterm=""
        )
    )
    if len(lines) > MAX_DIFF_LINES:
        lines = lines[:MAX_DIFF_LINES] + [DIFF_TRUNCATED]
    return "\n".join(lines)


def replace_text(text: str, old: str, new: str, replace_all: bool) -> tuple[str, int]:
    """Pure replacement with the uniqueness rule; returns the new text and the replacement count."""
    if not old:
        raise EditError("old_string must not be empty; use write_file to create a file")
    count = text.count(old)
    if count == 0:
        raise EditError("old_string was not found; read the file again and copy the exact text")
    if count > 1 and not replace_all:
        raise EditError(
            f"old_string occurs {count} times; add surrounding lines to make it unique "
            "or set replace_all"
        )
    return text.replace(old, new), count


def apply_change(ctx: ToolContext, target: Path, rel_path: str, before: str, after: str) -> bool:
    """Ask for approval with a diff, then write; False when the user declines."""
    if not ctx.approve(ToolPermission.WRITE, f"Edit {rel_path}?", make_diff(rel_path, before, after)):
        return False
    if not ctx.dry_run:
        ctx.before_write(str(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(after, encoding=FILE_ENCODING)
        ctx.on_edit(str(target))
    return True


def edit_file(
    ctx: ToolContext, path: str, old_string: str, new_string: str, replace_all: bool = False
) -> str:
    target = resolve_in_root(ctx.root, path)
    if not target.is_file():
        raise EditError(f"Not a file: {path!r}; use write_file to create it")
    before = target.read_text(encoding=FILE_ENCODING)
    after, count = replace_text(before, old_string, new_string, replace_all)
    if not apply_change(ctx, target, path, before, after):
        return DENIED_MESSAGE
    note = DRY_RUN_NOTE if ctx.dry_run else ""
    return f"Edited {path}: {count} replacement(s){note}"


def write_file(ctx: ToolContext, path: str, content: str) -> str:
    target = resolve_in_root(ctx.root, path)
    if target.is_dir():
        raise EditError(f"Is a directory: {path!r}")
    existed = target.exists()
    before = target.read_text(encoding=FILE_ENCODING) if existed else ""
    if not apply_change(ctx, target, path, before, content):
        return DENIED_MESSAGE
    note = DRY_RUN_NOTE if ctx.dry_run else ""
    return f"{'Overwrote' if existed else 'Created'} {path}{note}"


def register_edit_tools(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add edit_file and write_file, bound to `ctx`, to `registry`."""
    registry.register(
        "edit_file",
        "Replace an exact string in a project file. Read the file first and copy old_string exactly.",
        EDIT_PARAMETERS,
        lambda path, old_string, new_string, replace_all=False: edit_file(
            ctx, path, old_string, new_string, replace_all
        ),
    )
    registry.register(
        "write_file",
        "Create a new file or overwrite an existing one with the given content.",
        WRITE_PARAMETERS,
        lambda path, content: write_file(ctx, path, content),
    )
