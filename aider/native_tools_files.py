"""File-management tools: delete_file removes a project file and move_file renames or moves one.
They exist because a refactor that retires or relocates a file otherwise needs `rm` or `mv`, which the command
policy asks about every time and an unattended run can never get approved.
Both need WRITE approval with the affected content shown, snapshot the originals for /undo-agent, and report the
changed paths through ctx.on_edit like any other edit.
"""

from pathlib import Path

from aider.native_sensitive import is_sensitive
from aider.native_tool_context import DENIED_CHANGE, ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolRegistry
from aider.native_tools_builtin import FILE_ENCODING, resolve_in_root
from aider.native_tools_edit import DRY_RUN_NOTE, EditError, make_diff

BINARY_PREVIEW = "(binary file, {size} bytes)"
SENSITIVE_REFUSAL = "{path!r} may hold secrets and is usually untracked, so the agent never deletes or moves it; " \
    "ask the user to do it"
DELETE_PARAMETERS = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}
MOVE_PARAMETERS = {
    "type": "object",
    "properties": {
        "source": {"type": "string"},
        "destination": {"type": "string", "description": "New path of the file; must not exist yet."},
    },
    "required": ["source", "destination"],
}


def preview(target: Path, rel_path: str) -> str:
    """What the approval prompt shows for a file about to go: its content as a removal diff, or its size."""
    try:
        text = target.read_text(encoding=FILE_ENCODING)
    except UnicodeDecodeError:
        return BINARY_PREVIEW.format(size=target.stat().st_size)
    return make_diff(rel_path, text, "")


def remove_empty_parents(target: Path, root: Path) -> None:
    """Drop directories left empty by a removal, up to but never including the project root."""
    for parent in target.parents:
        if parent == root or root not in parent.parents or any(parent.iterdir()):
            return
        parent.rmdir()


def existing_file(ctx: ToolContext, path: str) -> Path:
    target = resolve_in_root(ctx.root, path)
    if is_sensitive(path):
        raise EditError(SENSITIVE_REFUSAL.format(path=path))
    if target.is_dir():
        raise EditError(f"Is a directory: {path!r}; name one file")
    if not target.is_file():
        raise EditError(f"Not a file: {path!r}")
    return target


def forget(ctx: ToolContext, target: Path) -> None:
    if ctx.file_state is not None:
        ctx.file_state.forget(target)


def delete_file(ctx: ToolContext, path: str) -> str:
    target = existing_file(ctx, path)
    if not ctx.approve(ToolPermission.WRITE, f"Delete {path}?", preview(target, path)):
        return DENIED_CHANGE
    if ctx.dry_run:
        return f"Deleted {path}{DRY_RUN_NOTE}"
    ctx.before_write(str(target))
    target.unlink()
    remove_empty_parents(target, ctx.root)
    forget(ctx, target)
    ctx.on_edit(str(target))
    return f"Deleted {path}"


def move_file(ctx: ToolContext, source: str, destination: str) -> str:
    origin = existing_file(ctx, source)
    target = resolve_in_root(ctx.root, destination)
    if is_sensitive(destination):
        raise EditError(SENSITIVE_REFUSAL.format(path=destination))
    if target.exists():
        raise EditError(f"Destination exists: {destination!r}; delete it first or choose another path")
    if not ctx.approve(ToolPermission.WRITE, f"Move {source} to {destination}?", f"{source} -> {destination}"):
        return DENIED_CHANGE
    if ctx.dry_run:
        return f"Moved {source} to {destination}{DRY_RUN_NOTE}"
    ctx.before_write(str(origin))
    ctx.before_write(str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    origin.rename(target)
    remove_empty_parents(origin, ctx.root)
    forget(ctx, origin)
    if ctx.file_state is not None:
        ctx.file_state.record(target)
    ctx.on_edit(str(origin))
    ctx.on_edit(str(target))
    return f"Moved {source} to {destination}; update the imports and references that name the old path"


def register_file_tools(registry: NativeToolRegistry, ctx: ToolContext) -> None:
    """Add delete_file and move_file, bound to `ctx`, to `registry`."""
    registry.register(
        "delete_file",
        "Delete one project file. Use it instead of rm.",
        DELETE_PARAMETERS,
        lambda path: delete_file(ctx, path),
    )
    registry.register(
        "move_file",
        "Move or rename one project file, keeping its content. Use it instead of mv.",
        MOVE_PARAMETERS,
        lambda source, destination: move_file(ctx, source, destination),
    )
