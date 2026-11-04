"""Tests for retrying an empty model reply instead of ending the session on it.
mlx_vlm answers empty when it rejects a malformed tool call, so an empty reply is usually one lost call, not the
model finishing. The retries must stay capped, because a server that only ever answers empty must still end.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, list_files_call, make_completion

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model
from aider.native_task_gates import EMPTY_REPLY_NUDGE, MAX_EMPTY_REPLY_RETRIES, may_retry_empty


class MayRetryEmptyTest(unittest.TestCase):
    def test_empty_text_retries(self) -> None:
        self.assertTrue(may_retry_empty("", 0))

    def test_whitespace_counts_as_empty(self) -> None:
        self.assertTrue(may_retry_empty(" \n ", 1))

    def test_a_real_answer_does_not_retry(self) -> None:
        self.assertFalse(may_retry_empty("Done.", 0))

    def test_the_cap_stops_retrying(self) -> None:
        self.assertFalse(may_retry_empty("", MAX_EMPTY_REPLY_RETRIES))


class EmptyReplyLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_with(self, replies: list) -> tuple:
        io = InputOutput(yes=True, pretty=False)
        coder = Coder.create(main_model=Model(MODEL_NAME), edit_format="agent", io=io, fnames=[], use_git=False,
                             map_tokens=0, auto_lint=False, stream=False)
        scripted = ScriptedModel(replies)
        with patch("aider.models.litellm.completion", side_effect=scripted):
            coder.run(with_message="List the files.")
        return coder, scripted

    def test_the_session_continues_after_an_empty_reply(self) -> None:
        replies = [make_completion(tool_calls=list_files_call("a")), make_completion(""), make_completion(FINAL_TEXT)]
        coder, scripted = self.run_with(replies)
        self.assertEqual(coder.partial_response_content, FINAL_TEXT)
        sent = [m.get("content") for call in scripted.requests[-1:] for m in call.get("messages", [])]
        self.assertIn(EMPTY_REPLY_NUDGE, sent)

    def test_a_server_that_only_answers_empty_still_ends(self) -> None:
        replies = [make_completion("") for _ in range(MAX_EMPTY_REPLY_RETRIES + 1)]
        _, scripted = self.run_with(replies)
        self.assertEqual(len(scripted.requests), MAX_EMPTY_REPLY_RETRIES + 1)


if __name__ == "__main__":
    unittest.main()
