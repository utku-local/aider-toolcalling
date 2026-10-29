"""Tests for the model-written summary of earlier tool rounds.
They check which span is summarized (everything before the last kept rounds), that the transcript is bounded, and
that the adapter rewrites both the live request list and cur_messages, leaving tool pairs valid.
A failing or empty model reply must leave the history unchanged.
"""

import json
import unittest
from types import SimpleNamespace

from aider.coders.native_context import maybe_summarize
from aider.native_context_summary import (
    MAX_TRANSCRIPT_CHARS,
    SUMMARY_HEADING,
    summary_span,
    transcript,
)
from aider.native_tool_loop import drop_orphan_tool_messages

BIG = "x" * 60_000


def round_messages(index: int, content: str = "ok") -> list[dict]:
    call = {"id": f"c{index}", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}
    return [{"role": "assistant", "content": "", "tool_calls": [call]},
            {"role": "tool", "tool_call_id": f"c{index}", "name": "read_file", "content": content}]


def history(rounds: int, content: str = "ok") -> list[dict]:
    messages = [{"role": "system", "content": "sys"}, {"role": "user", "content": "fix it"}]
    for index in range(rounds):
        messages += round_messages(index, content)
    return messages


class SpanTest(unittest.TestCase):
    def test_span_keeps_the_last_two_rounds(self) -> None:
        messages = history(5)
        start, end = summary_span(messages)
        self.assertEqual((start, end), (2, 8))
        self.assertIsNone(summary_span(history(2)))

    def test_transcript_is_bounded(self) -> None:
        self.assertLessEqual(len(transcript(history(200, BIG))), MAX_TRANSCRIPT_CHARS + 20)


class AdapterTest(unittest.TestCase):
    def make_coder(self, messages: list[dict], reply: object) -> SimpleNamespace:
        def send(request: list[dict]) -> object:
            if isinstance(reply, Exception):
                raise reply
            return reply

        return SimpleNamespace(main_model=SimpleNamespace(simple_send_with_retries=send),
                               io=SimpleNamespace(tool_output=lambda text: None, tool_warning=lambda text: None),
                               cur_messages=json.loads(json.dumps(messages[1:])))

    def test_summary_replaces_old_rounds_in_both_lists(self) -> None:
        messages = history(5, BIG)
        coder = self.make_coder(messages, "Goal: fix it. Found the bug in calc.py.")
        self.assertTrue(maybe_summarize(coder, messages))
        self.assertEqual(len(messages), 2 + 1 + 4)
        self.assertTrue(messages[2]["content"].startswith(SUMMARY_HEADING))
        self.assertEqual(messages, drop_orphan_tool_messages(messages))
        self.assertEqual(coder.cur_messages, messages[1:])

    def test_short_history_or_failed_model_changes_nothing(self) -> None:
        short = history(5)
        self.assertFalse(maybe_summarize(self.make_coder(short, "summary"), short))
        long = history(5, BIG)
        before = json.dumps(long)
        self.assertFalse(maybe_summarize(self.make_coder(long, RuntimeError("down")), long))
        self.assertFalse(maybe_summarize(self.make_coder(long, ""), long))
        self.assertEqual(json.dumps(long), before)
