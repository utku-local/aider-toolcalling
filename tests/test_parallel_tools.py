"""Tests for running read-only tool calls of one round concurrently.
Slow fake handlers show that safe calls overlap in time, while calls that may prompt (writes, secret reads) stay
sequential; results must come back in the order the model asked for them.
Each call is still recorded in the operation ledger.
"""

import json
import threading
import time
import unittest

from aider.native_tool_calls import ToolCall
from aider.native_tool_ledger import OperationLedger
from aider.native_tool_loop import build_tool_round_messages, runs_in_parallel
from aider.native_toolcalling import NativeToolRegistry

DELAY_SECONDS = 0.2
PATH_SCHEMA = {"type": "object", "properties": {"path": {"type": "string"}}}


class ParallelToolsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()
        self.registry = NativeToolRegistry()
        for name in ("read_file", "search_code", "edit_file"):
            self.registry.register(name, name, PATH_SCHEMA, self.slow(name))

    def slow(self, name: str):
        def handler(path: str) -> str:
            with self.lock:
                self.active += 1
                self.peak = max(self.peak, self.active)
            time.sleep(DELAY_SECONDS)
            with self.lock:
                self.active -= 1
            return f"{name}:{path}"
        return handler

    def call(self, call_id: str, name: str, path: str) -> ToolCall:
        return ToolCall(call_id, name, json.dumps({"path": path}))

    def test_safe_calls_overlap_and_keep_order(self) -> None:
        calls = [self.call(f"c{i}", "read_file", f"f{i}.py") for i in range(4)]
        ledger = OperationLedger()
        start = time.monotonic()
        out = build_tool_round_messages(self.registry, "", calls, ledger)
        elapsed = time.monotonic() - start
        self.assertEqual([m["content"] for m in out[1:]], [f"read_file:f{i}.py" for i in range(4)])
        self.assertGreater(self.peak, 1)
        self.assertLess(elapsed, DELAY_SECONDS * 3)
        self.assertEqual(len(ledger.records), 4)

    def test_calls_that_may_prompt_stay_sequential(self) -> None:
        calls = [self.call("e1", "edit_file", "a.py"), self.call("e2", "edit_file", "b.py"),
                 self.call("s1", "read_file", ".env")]
        out = build_tool_round_messages(self.registry, "", calls, OperationLedger())
        self.assertEqual(self.peak, 1)
        self.assertEqual([m["tool_call_id"] for m in out[1:]], ["e1", "e2", "s1"])

    def test_classification(self) -> None:
        self.assertTrue(runs_in_parallel(self.call("a", "search_code", "x")))
        self.assertTrue(runs_in_parallel(self.call("a", "read_file", "src/a.py")))
        self.assertFalse(runs_in_parallel(self.call("a", "read_file", "config/.env")))
        self.assertFalse(runs_in_parallel(self.call("a", "run_command", "x")))
        self.assertFalse(runs_in_parallel(ToolCall("a", "read_file", "{bad json")))


if __name__ == "__main__":
    unittest.main()
