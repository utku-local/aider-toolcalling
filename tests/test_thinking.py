"""Tests for the extended-thinking toggle used in agent mode.
They cover the pure extra_params surgery, the per-project persistence in .aider-agent.json, the config field
parsing, and the blank-answer fallback that shows the reasoning trace when a thinking model returns empty content.
No model and no network are needed; everything runs on plain dicts and a temporary directory.
"""

import json
import os
import tempfile
import unittest

from aider.coders.native_agent_config import (
    AgentConfigError,
    parse_config,
    read_thinking,
    write_thinking,
)
from aider.native_thinking import thinking_enabled, with_thinking
from aider.native_tool_calls import answer_text, reasoning_content, visible_content

ENABLE = ("extra_body", "chat_template_kwargs", "enable_thinking")


class WithThinkingTest(unittest.TestCase):
    def read_flag(self, params: dict) -> object:
        return params["extra_body"]["chat_template_kwargs"]["enable_thinking"]

    def test_none_leaves_params_unchanged(self) -> None:
        params = {"temperature": 0.7}
        self.assertIs(with_thinking(params, None), params)

    def test_enabling_sets_the_flag_on_empty_params(self) -> None:
        self.assertTrue(self.read_flag(with_thinking(None, True)))
        self.assertFalse(self.read_flag(with_thinking({}, False)))

    def test_other_extra_body_keys_are_kept(self) -> None:
        params = {"extra_body": {"top_k": 20, "chat_template_kwargs": {"other": 1}}}
        result = with_thinking(params, True)
        self.assertEqual(result["extra_body"]["top_k"], 20)
        self.assertEqual(result["extra_body"]["chat_template_kwargs"]["other"], 1)
        self.assertTrue(self.read_flag(result))

    def test_the_input_is_not_mutated(self) -> None:
        params = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        with_thinking(params, True)
        self.assertFalse(self.read_flag(params))

    def test_thinking_enabled_reads_the_flag(self) -> None:
        self.assertFalse(thinking_enabled(None))
        self.assertFalse(thinking_enabled({"extra_body": {}}))
        self.assertTrue(thinking_enabled(with_thinking(None, True)))
        self.assertFalse(thinking_enabled(with_thinking(None, False)))


class PersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_unset_reads_none(self) -> None:
        self.assertIsNone(read_thinking(self.root))

    def test_round_trip(self) -> None:
        write_thinking(self.root, True)
        self.assertTrue(read_thinking(self.root))
        write_thinking(self.root, False)
        self.assertFalse(read_thinking(self.root))

    def test_other_settings_are_preserved(self) -> None:
        path = os.path.join(self.root, ".aider-agent.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"sandbox": True}, handle)
        write_thinking(self.root, True)
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data, {"sandbox": True, "thinking": True})

    def test_malformed_file_reads_none(self) -> None:
        with open(os.path.join(self.root, ".aider-agent.json"), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIsNone(read_thinking(self.root))


class ParseConfigTest(unittest.TestCase):
    def test_thinking_defaults_to_none(self) -> None:
        self.assertIsNone(parse_config({}).thinking)

    def test_thinking_is_read(self) -> None:
        self.assertTrue(parse_config({"thinking": True}).thinking)

    def test_a_non_boolean_is_rejected(self) -> None:
        with self.assertRaises(AgentConfigError):
            parse_config({"thinking": "yes"})


class AnswerFallbackTest(unittest.TestCase):
    def test_content_is_used_when_present(self) -> None:
        self.assertEqual(answer_text({"content": "done", "reasoning": "thought"}), "done")

    def test_reasoning_is_used_when_content_is_empty(self) -> None:
        self.assertEqual(answer_text({"content": "", "reasoning": "the answer"}), "the answer")
        self.assertEqual(answer_text({"content": None, "reasoning_content": "via field"}), "via field")

    def test_empty_when_neither_is_present(self) -> None:
        self.assertEqual(answer_text({"content": ""}), "")
        self.assertEqual(reasoning_content({"content": "x"}), "")
        self.assertEqual(visible_content({"content": "x"}), "x")


if __name__ == "__main__":
    unittest.main()
