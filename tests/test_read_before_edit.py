"""Tests for the read-before-edit check and for saving long tool output to a file.
They check that an unread or externally changed file cannot be edited, that new files can be written, that the
agent's own writes keep the record current, and that long output is saved whole with a head-and-tail preview.
Everything runs on a temporary project through the real edit and read tools.
"""

import os
import tempfile
import unittest
from pathlib import Path

from aider.native_file_state import FileState, StaleFileError
from aider.native_output_spill import OUTPUT_DIR, OutputSpill, preview
from aider.native_tool_context import ToolContext
from aider.native_tools_builtin import guarded_read
from aider.native_tools_edit import edit_file, write_file


def make_ctx(root: Path, state: FileState, spill: OutputSpill = None) -> ToolContext:
    return ToolContext(root=root, list_files=lambda: [], find_tags=lambda a, b: [],
                       approve=lambda permission, title, details: True, on_edit=lambda path: None,
                       dry_run=False, file_state=state, spill=spill)


class ReadBeforeEditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        (self.root / "calc.py").write_text("x = 1\n")
        self.ctx = make_ctx(self.root, FileState())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unread_file_cannot_be_edited(self) -> None:
        with self.assertRaises(StaleFileError):
            edit_file(self.ctx, "calc.py", "x = 1", "x = 2")

    def test_read_then_edit_twice(self) -> None:
        guarded_read(self.ctx, "calc.py")
        edit_file(self.ctx, "calc.py", "x = 1", "x = 2")
        edit_file(self.ctx, "calc.py", "x = 2", "x = 3")
        self.assertEqual((self.root / "calc.py").read_text(), "x = 3\n")

    def test_external_change_forces_a_new_read(self) -> None:
        guarded_read(self.ctx, "calc.py")
        target = self.root / "calc.py"
        target.write_text("x = 10\n")
        os.utime(target, ns=(target.stat().st_atime_ns, target.stat().st_mtime_ns + 1_000_000))
        with self.assertRaises(StaleFileError):
            edit_file(self.ctx, "calc.py", "x = 10", "x = 11")

    def test_new_files_need_no_read(self) -> None:
        write_file(self.ctx, "new.py", "y = 1\n")
        edit_file(self.ctx, "new.py", "y = 1", "y = 2")
        self.assertEqual((self.root / "new.py").read_text(), "y = 2\n")


class OutputSpillTest(unittest.TestCase):
    def test_long_output_is_saved_with_a_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spill = OutputSpill(Path(tmp))
            text = "head\n" + "x" * 50_000 + "\ntail error"
            shown = spill.shorten(text, "command")
            saved = Path(tmp) / OUTPUT_DIR / "command-1.txt"
            self.assertEqual(saved.read_text(), text)
            self.assertTrue(shown.startswith("head"))
            self.assertTrue(shown.endswith("tail error"))
            self.assertIn(str(OUTPUT_DIR / "command-1.txt"), shown)
            self.assertEqual((Path(tmp) / ".aider-agent" / ".gitignore").read_text(), "*\n")

    def test_preview_is_short(self) -> None:
        self.assertLess(len(preview("a" * 100_000, "out.txt")), 21_000)
