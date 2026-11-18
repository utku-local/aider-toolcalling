"""Tests for the command shapes the policy judges part by part: quoted newlines, here-documents and lists.
Each case is plain text in and a parsed shape out; nothing is executed.
The refusals matter most: a here-document is trusted only when nothing can run besides the command on its first line.
"""

import unittest

from aider.native_command_shape import has_unquoted_newline, list_segments, without_heredoc


class CommandShapeTest(unittest.TestCase):
    def test_newlines_inside_quotes_are_argument_text(self) -> None:
        for command in ('python -c "a\nb"', "python -c 'a\nb'", 'echo "it\'s\nfine"', "pytest\n", 'echo "a\\"\nb"'):
            with self.subTest(command=command):
                self.assertFalse(has_unquoted_newline(command))
        for command in ("pytest\nrm x", 'echo "a"\nls', "echo 'a\nb'\nls", 'echo a\\"\nls'):
            with self.subTest(command=command):
                self.assertTrue(has_unquoted_newline(command))

    def test_literal_heredoc_reduces_to_its_command(self) -> None:
        cases = {
            "python3 - <<'EOF'\nprint(1)\nEOF": "python3 -",
            'python3 <<"PY"\nprint("$HOME")\nPY\n': "python3",
            "python3 - <<EOF\nprint(1)\nEOF": "python3 -",
            "python3 - <<-'EOF'\n\tprint(1)\n\tEOF": "python3 -",
        }
        for command, head in cases.items():
            with self.subTest(command=command):
                self.assertEqual(without_heredoc(command), head)

    def test_untrusted_heredocs_are_left_alone(self) -> None:
        for command in (
            "python3 - <<EOF\nprint('$HOME')\nEOF",
            "python3 - <<EOF\nprint(`id`)\nEOF",
            "python3 - <<'EOF'\nprint(1)\nEOF\nrm -rf x",
            "python3 - <<'EOF'\nprint(1)\nEOF\nrm x\nEOF",
            "python3 - <<'EOF' && rm x\nprint(1)\nEOF",
            "python3 < in.txt <<'EOF'\nx\nEOF",
            "<<'EOF'\nx\nEOF",
            "python3 script.py",
        ):
            with self.subTest(command=command):
                self.assertIsNone(without_heredoc(command))

    def test_list_segments_keep_empty_parts(self) -> None:
        self.assertEqual(list_segments(["a", "x", "&&", "b", ";", "c", "||", "d"]), [["a", "x"], ["b"], ["c"], ["d"]])
        self.assertEqual(list_segments(["a", "|", "tail"]), [["a", "|", "tail"]])
        self.assertEqual(list_segments(["a", "&&"]), [["a"], []])


if __name__ == "__main__":
    unittest.main()
