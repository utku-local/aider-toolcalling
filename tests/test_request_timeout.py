"""Tests for what the agent does when a model request times out.
A timed-out request must not be sent again in agent mode, because a local server is still generating it; other
connection errors keep upstream's retry, and chat modes without native tools are unchanged.
The flow test scripts the model's replies and errors, so no server is involved.
"""

import os
import tempfile
import unittest
from unittest.mock import patch

import litellm
from test_agent_coder import tool_call
from test_coder_native_tools import FINAL_TEXT, MODEL_NAME, ScriptedModel, make_completion

from aider.coders import Coder
from aider.coders.native_subtask import SUBTASK_TIMEOUT
from aider.io import InputOutput
from aider.models import Model
from aider.native_request_timeout import AGENT_REQUEST_TIMEOUT_SECONDS, agent_timeout, is_timeout

USER_TIMEOUT = 45.0


class TimeoutRulesTest(unittest.TestCase):
    def test_is_timeout(self) -> None:
        self.assertTrue(is_timeout("Timeout", "Request timed out."))
        self.assertTrue(is_timeout("APIConnectionError", "APIConnectionError: OpenAIException - timed out"))
        self.assertFalse(is_timeout("APIConnectionError", "Connection refused"))
        self.assertFalse(is_timeout("RateLimitError", "slow down"))

    def test_agent_timeout(self) -> None:
        self.assertEqual(agent_timeout(None, agent=True), AGENT_REQUEST_TIMEOUT_SECONDS)
        self.assertIsNone(agent_timeout(None, agent=False))
        self.assertEqual(agent_timeout(USER_TIMEOUT, agent=True), USER_TIMEOUT)
        self.assertEqual(agent_timeout(USER_TIMEOUT, agent=False), USER_TIMEOUT)


class TimeoutFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        with open(os.path.join(self.tmp.name, "calc.py"), "w") as handle:
            handle.write("def add(a, b):\n    return a - b\n")
        self.cwd = os.getcwd()
        os.chdir(self.tmp.name)

    def tearDown(self) -> None:
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def run_agent(self, error: Exception) -> ScriptedModel:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        scripted = ScriptedModel([
            make_completion(tool_calls=tool_call("r0", "read_file", {"path": "calc.py"})),
            error, make_completion(FINAL_TEXT), make_completion(FINAL_TEXT),
        ])
        take = scripted.__call__

        def respond(**kwargs: object) -> object:
            result = take(**kwargs)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("aider.models.litellm.completion", side_effect=respond):
            coder.run(with_message="Look at add().")
        self.assertEqual(len(coder.native_ledger.records), 1)
        return scripted

    def test_a_timed_out_request_is_not_sent_again(self) -> None:
        for error in (
            litellm.Timeout(message="Request timed out.", llm_provider="openai", model=MODEL_NAME),
            litellm.APIConnectionError(message="OpenAIException - timed out", llm_provider="openai",
                                       model=MODEL_NAME),
        ):
            with self.subTest(error=type(error).__name__):
                self.assertEqual(len(self.run_agent(error).requests), 2)

    def test_a_sub_agent_timeout_becomes_its_answer_and_is_not_re_sent(self) -> None:
        coder = Coder.create(
            main_model=Model(MODEL_NAME), edit_format="agent", io=InputOutput(yes=True, pretty=False),
            fnames=[], use_git=False, map_tokens=0, auto_lint=False, stream=False,
        )
        timeout = litellm.Timeout(message="Request timed out.", llm_provider="openai", model=MODEL_NAME)
        scripted = ScriptedModel([
            make_completion(tool_calls=tool_call("q1", "research", {"question": "Where is add defined?"})),
            timeout, make_completion(FINAL_TEXT),
        ])
        take = scripted.__call__

        def respond(**kwargs: object) -> object:
            result = take(**kwargs)
            if isinstance(result, Exception):
                raise result
            return result

        with patch("aider.models.litellm.completion", side_effect=respond):
            coder.run(with_message="Find add().")
        self.assertEqual(len(scripted.requests), 3)
        results = [m["content"] for m in scripted.requests[-1]["messages"] if m.get("tool_call_id") == "q1"]
        self.assertEqual(results, [SUBTASK_TIMEOUT])

    def test_another_connection_error_is_still_retried(self) -> None:
        outage = litellm.APIConnectionError(message="Connection refused", llm_provider="openai", model=MODEL_NAME)
        self.assertEqual(len(self.run_agent(outage).requests), 3)


if __name__ == "__main__":
    unittest.main()
