"""Tests for delete_file and move_file against a temporary project directory.
They cover approval with the content shown, declines and dry runs, snapshots that /undo-agent restores, empty
directories left behind, and the refusals: directories, existing destinations, paths outside the root and secrets.
A ToolContext built from plain functions records approvals and edits, so no Aider io or model is involved.
"""

import tempfile
import unittest
from pathlib import Path

from aider.native_file_state import FileState
from aider.native_snapshots import SnapshotStore
from aider.native_tool_context import DENIED_CHANGE, ToolContext, ToolPermission
from aider.native_tool_ledger import CHANGE_TOOLS
from aider.native_toolcalling import NativeToolRegistry
from aider.native_tools_builtin import ToolPathError
from aider.native_tools_edit import EditError
from aider.native_tools_files import delete_file, move_file, register_file_tools

FILES = {"pkg/old.py": "VALUE = 1\n", "pkg/keep.py": "KEEP = 2\n", "deep/a/b/only.txt": "x\n", ".env": "KEY=1\n"}
REQUEST = 1


class FileToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        for rel, text in FILES.items():
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_text(text)
        self.asked: list[tuple[ToolPermission, str, str]] = []
        self.edited: list[str] = []
        self.snapshots = SnapshotStore()
        self.state = FileState()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def ctx(self, answer: bool = True, dry_run: bool = False) -> ToolContext:
        def approve(permission: ToolPermission, title: str, details: str) -> bool:
            self.asked.append((permission, title, details))
            return answer

        return ToolContext(
            root=self.root, list_files=lambda: sorted(FILES), find_tags=lambda a, r: [], approve=approve,
            on_edit=self.edited.append, dry_run=dry_run,
            before_write=lambda path: self.snapshots.capture(REQUEST, path), file_state=self.state,
        )

    def test_delete_asks_with_the_content_and_can_be_undone(self) -> None:
        self.state.record(self.root / "pkg/old.py")
        self.assertEqual(delete_file(self.ctx(), "pkg/old.py"), "Deleted pkg/old.py")
        self.assertFalse((self.root / "pkg/old.py").exists())
        permission, title, details = self.asked[0]
        self.assertIs(permission, ToolPermission.WRITE)
        self.assertEqual(title, "Delete pkg/old.py?")
        self.assertIn("-VALUE = 1", details)
        self.assertEqual(self.edited, [str(self.root / "pkg/old.py")])
        self.assertFalse(self.state.unchanged(self.root / "pkg/old.py"))
        self.snapshots.undo_latest()
        self.assertEqual((self.root / "pkg/old.py").read_text(), FILES["pkg/old.py"])

    def test_delete_removes_emptied_directories_and_undo_recreates_them(self) -> None:
        delete_file(self.ctx(), "deep/a/b/only.txt")
        self.assertFalse((self.root / "deep").exists())
        self.assertTrue(self.root.is_dir())
        delete_file(self.ctx(), "pkg/old.py")
        self.assertTrue((self.root / "pkg/keep.py").exists())
        self.snapshots.undo_latest()
        self.assertEqual((self.root / "deep/a/b/only.txt").read_text(), "x\n")

    def test_declined_and_dry_run_change_nothing(self) -> None:
        self.assertEqual(delete_file(self.ctx(answer=False), "pkg/old.py"), DENIED_CHANGE)
        self.assertEqual(move_file(self.ctx(answer=False), "pkg/old.py", "pkg/new.py"), DENIED_CHANGE)
        self.assertIn("dry run", delete_file(self.ctx(dry_run=True), "pkg/old.py"))
        self.assertIn("dry run", move_file(self.ctx(dry_run=True), "pkg/old.py", "pkg/new.py"))
        self.assertTrue((self.root / "pkg/old.py").exists())
        self.assertFalse((self.root / "pkg/new.py").exists())
        self.assertEqual(self.edited, [])

    def test_move_keeps_content_reports_both_paths_and_can_be_undone(self) -> None:
        result = move_file(self.ctx(), "deep/a/b/only.txt", "moved/here.txt")
        self.assertTrue(result.startswith("Moved deep/a/b/only.txt to moved/here.txt"))
        self.assertEqual((self.root / "moved/here.txt").read_text(), "x\n")
        self.assertFalse((self.root / "deep").exists())
        self.assertEqual(self.edited, [str(self.root / "deep/a/b/only.txt"), str(self.root / "moved/here.txt")])
        self.assertTrue(self.state.unchanged(self.root / "moved/here.txt"))
        self.snapshots.undo_latest()
        self.assertEqual((self.root / "deep/a/b/only.txt").read_text(), "x\n")
        self.assertFalse((self.root / "moved/here.txt").exists())

    def test_refusals(self) -> None:
        ctx = self.ctx()
        refused = (
            lambda: delete_file(ctx, "pkg"), lambda: delete_file(ctx, "missing.py"), lambda: delete_file(ctx, ".env"),
            lambda: move_file(ctx, "pkg/old.py", "pkg/keep.py"), lambda: move_file(ctx, ".env", "env.txt"),
            lambda: move_file(ctx, "pkg/old.py", "config/.env"), lambda: move_file(ctx, "missing.py", "x.py"),
        )
        for number, call in enumerate(refused):
            with self.subTest(number=number), self.assertRaises(EditError):
                call()
        for call in (lambda: delete_file(ctx, "../outside.txt"), lambda: move_file(ctx, "pkg/old.py", "../out.py")):
            with self.assertRaises(ToolPathError):
                call()
        self.assertEqual(self.asked, [])
        self.assertEqual({rel for rel in FILES if (self.root / rel).exists()}, set(FILES))

    def test_binary_file_is_previewed_by_size(self) -> None:
        (self.root / "blob.bin").write_bytes(b"\xff\xfe\x00\x01")
        delete_file(self.ctx(), "blob.bin")
        self.assertEqual(self.asked[0][2], "(binary file, 4 bytes)")

    def test_registered_as_change_tools(self) -> None:
        registry = NativeToolRegistry()
        register_file_tools(registry, self.ctx())
        names = {tool["function"]["name"] for tool in registry.schemas()}
        self.assertEqual(names, {"delete_file", "move_file"})
        self.assertTrue(names <= CHANGE_TOOLS)


if __name__ == "__main__":
    unittest.main()
