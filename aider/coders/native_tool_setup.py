"""Builds the native tool registry for a Coder and adapts the Coder to the ToolContext the tools expect.
Read and search tools are always included; edit and shell tools only when the caller asks for actions (agent mode).
Approvals go through Aider's io.confirm_ask: writes share a per-request confirm group, commands are asked every time.
"""

import os
from pathlib import Path
from typing import Any

from aider.io import ConfirmGroup
from aider.native_tool_context import ToolContext, ToolPermission
from aider.native_toolcalling import NativeToolRegistry
from aider.native_tools_builtin import register_read_tools
from aider.native_tools_edit import register_edit_tools
from aider.native_tools_search import register_search_tools
from aider.native_tools_shell import register_shell_tools
from aider.repomap import RepoMap

SKIPPED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", ".mypy_cache"})
HIDDEN_PREFIX = "."
MAX_WALKED_FILES = 20_000
SYMBOL_MAP_TOKENS = 1024


def walk_files(root: Path) -> list[str]:
    """Project files without a git repo: skip hidden and dependency directories."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            d for d in dirnames if d not in SKIPPED_DIRS and not d.startswith(HIDDEN_PREFIX)
        ]
        for name in filenames:
            found.append(Path(dirpath, name).relative_to(root).as_posix())
            if len(found) >= MAX_WALKED_FILES:
                return sorted(found)
    return sorted(found)


def project_files(coder: Any) -> list[str]:
    """Tracked files plus files the tools created this session; a directory walk without git."""
    if not coder.repo:
        return walk_files(Path(coder.root))
    created = {coder.get_rel_fname(path) for path in coder.native_tool_edits}
    return sorted(set(coder.get_all_relative_files()) | created)


def symbol_tags(coder: Any, abs_path: str, rel_path: str) -> list[Any]:
    if coder.native_symbol_map is None:
        coder.native_symbol_map = coder.repo_map or RepoMap(
            SYMBOL_MAP_TOKENS, coder.root, coder.main_model, coder.io
        )
    try:
        return list(coder.native_symbol_map.get_tags(abs_path, rel_path) or [])
    except Exception:  # unparsable files simply have no symbols
        return []


def approve(coder: Any, permission: ToolPermission, title: str, details: str) -> bool:
    if permission is ToolPermission.READ:
        return True
    if permission is ToolPermission.WRITE:
        return coder.io.confirm_ask(title, subject=details, group=coder.native_write_group)
    return coder.io.confirm_ask(title, subject=details, explicit_yes_required=True)


def record_edit(coder: Any, abs_path: str) -> None:
    """Remember a tool edit for the whole session (file listing) and for the current reply (post-edit flow)."""
    coder.native_tool_edits.add(abs_path)
    coder.native_pending_edits.add(abs_path)


def make_tool_context(coder: Any) -> ToolContext:
    return ToolContext(
        root=Path(coder.root).resolve(),
        list_files=lambda: project_files(coder),
        find_tags=lambda abs_path, rel_path: symbol_tags(coder, abs_path, rel_path),
        approve=lambda permission, title, details: approve(coder, permission, title, details),
        on_edit=lambda path: record_edit(coder, path),
        dry_run=bool(coder.dry_run),
    )


def build_native_tools(coder: Any, include_actions: bool) -> NativeToolRegistry:
    """Registry for `coder`; `include_actions` adds edit_file, write_file and run_command."""
    coder.native_tool_edits = set()
    coder.native_pending_edits = set()
    coder.native_write_group = ConfirmGroup()
    coder.native_symbol_map = None
    ctx = make_tool_context(coder)
    registry = NativeToolRegistry()
    register_read_tools(registry, ctx.root)
    register_search_tools(registry, ctx)
    if include_actions:
        register_edit_tools(registry, ctx)
        register_shell_tools(registry, ctx)
    return registry
