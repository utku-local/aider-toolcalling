"""Tests that a one-shot --message run does not start the background chat-history summary.
The summary thread outlived such runs and failed at interpreter shutdown with "cannot schedule new futures".
Interactive sessions still summarize when the history grows too big.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from test_coder_native_tools import MODEL_NAME

from aider.coders import Coder
from aider.io import InputOutput
from aider.main import main
from aider.models import Model


def make_coder() -> Coder:
    return Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
                        fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False)


class OneShotSummaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def test_summary_starts_only_when_enabled(self) -> None:
        coder = make_coder()
        coder.done_messages = [{"role": "user", "content": "hi"}]
        with patch.object(coder.summarizer, "too_big", return_value=True), \
                patch.object(coder, "summarize_worker"):
            coder.summarize_history = False
            coder.summarize_start()
            self.assertIsNone(coder.summarizer_thread)
            coder.summarize_history = True
            coder.summarize_start()
            self.assertIsNotNone(coder.summarizer_thread)
            coder.summarize_end()

    def test_message_run_turns_the_summary_off(self) -> None:
        seen = []
        with patch.object(Coder, "run", lambda coder, with_message=None: seen.append(coder.summarize_history)):
            main(["--message", "hi", "--no-git", "--yes-always", "--no-check-update", "--analytics-disable",
                  "--model", MODEL_NAME], input=None, output=None)
        self.assertEqual(seen, [False])


if __name__ == "__main__":
    unittest.main()
