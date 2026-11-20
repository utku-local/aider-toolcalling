"""Tests for when the ledger treats a file change as already applied in the current request.
A repeated identical change is refused, but not after another call replaced or removed a whole file.
The measured case is a check script written, deleted, written again and deleted again.
"""

import json
import unittest

from aider.native_tool_ledger import OperationLedger


def run(ledger: OperationLedger, tool: str, **arguments: str) -> str:
    text = json.dumps(arguments)
    entry = ledger.begin(f"id{len(ledger.records)}", tool, text)
    ledger.finish(entry, "ok", failed=False)
    return text


class AppliedBeforeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = OperationLedger()
        self.ledger.start_request()

    def test_a_repeated_edit_is_applied_even_after_other_edits(self) -> None:
        first = run(self.ledger, "edit_file", path="a.py", old_string="x", new_string="y")
        run(self.ledger, "edit_file", path="a.py", old_string="p", new_string="q")
        self.assertTrue(self.ledger.applied_before("edit_file", first))

    def test_a_second_delete_after_the_file_was_written_again_is_new(self) -> None:
        run(self.ledger, "write_file", path="check.py", content="one")
        delete = run(self.ledger, "delete_file", path="check.py")
        self.assertTrue(self.ledger.applied_before("delete_file", delete))
        run(self.ledger, "write_file", path="check.py", content="two")
        self.assertFalse(self.ledger.applied_before("delete_file", delete))

    def test_the_same_write_after_a_delete_is_new(self) -> None:
        write = run(self.ledger, "write_file", path="check.py", content="one")
        run(self.ledger, "delete_file", path="check.py")
        self.assertFalse(self.ledger.applied_before("write_file", write))

    def test_an_earlier_request_does_not_count(self) -> None:
        write = run(self.ledger, "write_file", path="check.py", content="one")
        self.ledger.start_request()
        self.assertFalse(self.ledger.applied_before("write_file", write))


if __name__ == "__main__":
    unittest.main()
