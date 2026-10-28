"""Unit tests for the read-only built-in tools in aider.native_tools_builtin.
Each test works in a temporary directory that plays the project root.
They check normal reads and listings, truncation, and that paths escaping the root are rejected.
"""

import tempfile
import unittest
from pathlib import Path

from aider.native_tools_builtin import (
    MAX_LIST_ENTRIES,
    DEFAULT_MAX_LINES,
    MAX_READ_CHARS,
    TRUNCATED_NOTE,
    ToolPathError,
    build_builtin_registry,
    list_files,
    read_file,
)


class NativeToolsBuiltinTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve() / "project"
        (self.root / "src").mkdir(parents=True)
        (self.root / "src" / "app.py").write_text("print('hi')\n")
        (self.root / "README.md").write_text("readme\n")
        (Path(self.tmp.name) / "secret.txt").write_text("secret\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_read_file_inside_root(self) -> None:
        self.assertEqual(read_file(self.root, "src/app.py"), "print('hi')\n")

    def test_list_files_marks_directories(self) -> None:
        self.assertEqual(list_files(self.root), "README.md\nsrc/")
        self.assertEqual(list_files(self.root, "src"), "app.py")

    def test_paths_outside_root_are_rejected(self) -> None:
        outside = str(Path(self.tmp.name) / "secret.txt")
        for path in ("../secret.txt", outside, "src/../../secret.txt"):
            with self.subTest(path=path), self.assertRaises(ToolPathError):
                read_file(self.root, path)
        with self.assertRaises(ToolPathError):
            list_files(self.root, "..")

    def test_wrong_kind_is_rejected(self) -> None:
        with self.assertRaises(ToolPathError):
            read_file(self.root, "src")
        with self.assertRaises(ToolPathError):
            list_files(self.root, "README.md")

    def test_large_outputs_are_truncated(self) -> None:
        (self.root / "big.txt").write_text("x" * (MAX_READ_CHARS + 10))
        self.assertTrue(read_file(self.root, "big.txt").endswith(TRUNCATED_NOTE))
        many = self.root / "many"
        many.mkdir()
        for i in range(MAX_LIST_ENTRIES + 1):
            (many / f"f{i:04d}").touch()
        self.assertTrue(list_files(self.root, "many").endswith(TRUNCATED_NOTE))

    def test_large_files_are_read_in_parts_without_a_range(self) -> None:
        lines = "".join(f"line {i}\n" for i in range(1, DEFAULT_MAX_LINES + 51))
        (self.root / "long.py").write_text(lines)
        partial = read_file(self.root, "long.py")
        self.assertTrue(partial.startswith("line 1\n"))
        self.assertIn(f"showing lines 1-{DEFAULT_MAX_LINES} of {DEFAULT_MAX_LINES + 50}", partial)
        self.assertNotIn(f"line {DEFAULT_MAX_LINES + 1}\n", partial)
        tail = read_file(self.root, "long.py", DEFAULT_MAX_LINES + 1, DEFAULT_MAX_LINES + 50)
        self.assertTrue(tail.startswith(f"line {DEFAULT_MAX_LINES + 1}\n"))
        self.assertNotIn("showing lines", tail)

    def test_registry_exposes_both_tools(self) -> None:
        registry = build_builtin_registry(str(self.root))
        names = [schema["function"]["name"] for schema in registry.schemas()]
        self.assertEqual(names, ["read_file", "list_files"])


if __name__ == "__main__":
    unittest.main()
