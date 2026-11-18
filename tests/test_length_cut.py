"""Tests for a reply cut off at the output limit in agent mode.
The cut reply is shortened and marked, the model is sent back to act a limited number of times, and a chat mode
without native tools still raises upstream's FinishReasonLength.
The flow test scripts the model's replies, so no server is involved.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_length_cut import (
    CUT_MARKER,
    KEPT_CHARS,
    LENGTH_CUT_NUDGE,
    MAX_LENGTH_CUT_NUDGES,
    may_nudge_length_cut,
    shorten_cut_reply,
)

LENGTH = "length"
RAMBLE = "Actually wait, let me think again. " * 400


def cut_completion(text: str) -> object:
    completion = make_completion(text)
    completion.choices[0].finish_reason = LENGTH
    return completion


class LengthCutTest(unittest.TestCase):
    def test_shorten_keeps_the_start_and_marks_the_cut(self) -> None:
        shortened = shorten_cut_reply(RAMBLE)
        self.assertTrue(shortened.endswith(CUT_MARKER))
        self.assertLessEqual(len(shortened), KEPT_CHARS + len(CUT_MARKER))
        self.assertEqual(shorten_cut_reply("short"), "short" + CUT_MARKER)

    def test_allowance(self) -> None:
        self.assertTrue(may_nudge_length_cut(MAX_LENGTH_CUT_NUDGES - 1))
        self.assertFalse(may_nudge_length_cut(MAX_LENGTH_CUT_NUDGES))


class LengthCutFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_agent(self, replies: list) -> tuple[Coder, ScriptedModel]:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        scripted = ScriptedModel(replies)
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="Fix the scheduler.")
        return coder, scripted

    def test_a_cut_reply_is_sent_back_and_the_request_goes_on(self) -> None:
        coder, scripted = self.run_agent([cut_completion(RAMBLE), make_completion(FINAL_TEXT)])
        self.assertEqual(len(scripted.requests), 2)
        nudges = [m for m in scripted.requests[1]["messages"] if m.get("content") == LENGTH_CUT_NUDGE]
        self.assertEqual(len(nudges), 1)
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)
        self.assertEqual(coder.num_exhausted_context_windows, 0)

    def test_the_allowance_ends_a_model_that_only_rambles(self) -> None:
        replies = [cut_completion(RAMBLE) for _ in range(MAX_LENGTH_CUT_NUDGES + 1)]
        _, scripted = self.run_agent(replies)
        self.assertEqual(len(scripted.requests), MAX_LENGTH_CUT_NUDGES + 1)


if __name__ == "__main__":
    unittest.main()
