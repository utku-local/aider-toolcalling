"""Tests for read_reply, which falls back to plain input() when prompt_toolkit cannot use stdin.
The unit tests pass plain functions as the prompt and the fallback, so no terminal is involved.
One test runs confirm_ask in a subprocess with stdin from /dev/null, the case that raised Errno 22 on macOS.
"""

import errno
import subprocess
import sys
import unittest
from pathlib import Path

from aider.prompt_fallback import read_reply

REPO_ROOT = Path(__file__).resolve().parent.parent
QUESTION = "Run this command? "
DEVNULL_SCRIPT = (
    "from aider.io import InputOutput\n"
    "io = InputOutput(pretty=True, fancy_input=True)\n"
    "print('approved=%s' % io.confirm_ask('Run this command?', subject='ls', explicit_yes_required=True))\n"
    "print('reply=%r' % io.prompt_ask('What now?', default='fallback-default'))\n"
)
SUBPROCESS_TIMEOUT_SECS = 60


def unwatchable() -> str:
    raise OSError(errno.EINVAL, "Invalid argument")


def end_of_input(question: str) -> str:
    raise EOFError


class ReadReplyTest(unittest.TestCase):
    def test_prompt_reply_is_returned(self) -> None:
        self.assertEqual(read_reply(lambda: "y", QUESTION, fallback=end_of_input), "y")

    def test_unwatchable_stdin_uses_the_fallback(self) -> None:
        asked = []

        def fallback(question: str) -> str:
            asked.append(question)
            return "n"

        self.assertEqual(read_reply(unwatchable, QUESTION, fallback=fallback), "n")
        self.assertEqual(asked, [QUESTION])

    def test_end_of_input_still_propagates(self) -> None:
        with self.assertRaises(EOFError):
            read_reply(unwatchable, QUESTION, fallback=end_of_input)

        def prompt_at_eof() -> str:
            raise EOFError

        with self.assertRaises(EOFError):
            read_reply(prompt_at_eof, QUESTION, fallback=end_of_input)


class DevNullStdinTest(unittest.TestCase):
    def test_prompts_take_their_default_with_stdin_from_devnull(self) -> None:
        with open("/dev/null") as devnull:
            done = subprocess.run(
                [sys.executable, "-c", DEVNULL_SCRIPT],
                cwd=REPO_ROOT,
                stdin=devnull,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECS,
            )
        self.assertNotIn("Errno 22", done.stdout + done.stderr)
        self.assertIn("approved=True", done.stdout)
        self.assertIn("reply='fallback-default'", done.stdout)


if __name__ == "__main__":
    unittest.main()
