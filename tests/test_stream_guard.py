"""Tests for the streamed-reply repetition guard in aider.native_stream_guard.
They cover the no-repetition case, tripping on a long identical line repeated past the threshold, the threshold and
minimum-length boundaries, trivial and blank lines that must not trip, repetition that is not at the tail, and that a
tripped reply is trimmed to a single copy with its earlier content preserved. Everything runs on plain strings.
"""

import unittest

from aider.native_stream_guard import (
    MIN_REPEATS,
    MIN_UNIT_CHARS,
    TAIL_WINDOW,
    collapse_runaway_repetition,
)

LINE = "Attack Flow Example section, and update the file-structure list to include"


class CollapseRunawayRepetitionTest(unittest.TestCase):
    def test_plain_text_does_not_trip(self) -> None:
        text = "Here is my answer.\nIt has several distinct lines.\nNothing repeats here.\n"
        self.assertEqual(collapse_runaway_repetition(text), (text, False))

    def test_a_long_line_repeated_past_the_threshold_trips(self) -> None:
        text = "intro line\n" + (LINE + "\n") * MIN_REPEATS + "partial tail"
        collapsed, tripped = collapse_runaway_repetition(text)
        self.assertTrue(tripped)
        self.assertEqual(collapsed, "intro line\n" + LINE + "\n")

    def test_one_fewer_than_the_threshold_does_not_trip(self) -> None:
        text = "intro\n" + (LINE + "\n") * (MIN_REPEATS - 1) + "next"
        self.assertEqual(collapse_runaway_repetition(text), (text, False))

    def test_short_lines_never_trip(self) -> None:
        short = "x" * (MIN_UNIT_CHARS - 1)
        text = (short + "\n") * (MIN_REPEATS + 3) + "tail"
        self.assertEqual(collapse_runaway_repetition(text), (text, False))

    def test_blank_lines_never_trip(self) -> None:
        text = "\n" * (MIN_REPEATS + 5) + "tail"
        self.assertEqual(collapse_runaway_repetition(text), (text, False))

    def test_repetition_not_at_the_tail_does_not_trip(self) -> None:
        text = (LINE + "\n") * MIN_REPEATS + "then the model moved on to say something else entirely here.\n"
        # The repeated block is no longer the trailing run, so there is nothing runaway to cut off.
        self.assertEqual(collapse_runaway_repetition(text), (text, False))

    def test_trip_keeps_exactly_one_copy(self) -> None:
        text = (LINE + "\n") * (MIN_REPEATS + 10)
        collapsed, tripped = collapse_runaway_repetition(text)
        self.assertTrue(tripped)
        self.assertEqual(collapsed.count(LINE), 1)

    def test_long_head_is_preserved_when_a_tail_loop_trips(self) -> None:
        head = ("A unique sentence number %d that does not repeat.\n" % n for n in range(200))
        prefix = "".join(head)
        self.assertGreater(len(prefix), TAIL_WINDOW)
        collapsed, tripped = collapse_runaway_repetition(prefix + (LINE + "\n") * MIN_REPEATS)
        self.assertTrue(tripped)
        self.assertTrue(collapsed.startswith(prefix))
        self.assertEqual(collapsed.count(LINE), 1)

    def test_empty_text_does_not_trip(self) -> None:
        self.assertEqual(collapse_runaway_repetition(""), ("", False))


if __name__ == "__main__":
    unittest.main()
