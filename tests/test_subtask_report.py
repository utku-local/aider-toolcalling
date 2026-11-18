"""Tests for the footer added to a task sub-agent's report.
The footer is built from ledger records only, so it must say which commands really ran, which did not, and which
files changed, whatever the report text claims.
Records are created through the ledger the tool loop uses; no model or project is involved.
"""

import json
import unittest

from aider.native_subtask_report import COMMANDS_RAN, FOOTER_HEADING, NO_COMMAND_RAN, task_footer
from aider.native_tool_ledger import OperationLedger, OperationStatus


def record(ledger: OperationLedger, call_id: str, tool: str, arguments: dict, result: str,
           status: OperationStatus = OperationStatus.EXECUTED) -> None:
    entry = ledger.begin(call_id, tool, json.dumps(arguments))
    if status is OperationStatus.DENIED:
        ledger.mark(OperationStatus.DENIED)
    ledger.finish(entry, result, failed=status is OperationStatus.FAILED)


class TaskFooterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = OperationLedger()
        self.ledger.start_request()

    def test_no_command_ran_is_stated_even_with_no_records(self) -> None:
        self.assertEqual(task_footer([]), f"{FOOTER_HEADING}\n{NO_COMMAND_RAN}")

    def test_unapproved_command_is_counted_and_not_listed_as_run(self) -> None:
        record(self.ledger, "c1", "run_command", {"command": "python -m app"}, "Not run", OperationStatus.DENIED)
        record(self.ledger, "r1", "read_file", {"path": "app.py"}, "3 lines")
        footer = task_footer(self.ledger.records)
        self.assertIn(NO_COMMAND_RAN, footer)
        self.assertIn("not run (not approved, refused or failed to start): 1", footer)
        self.assertNotIn("python -m app", footer)

    def test_commands_and_changed_files_are_listed(self) -> None:
        record(self.ledger, "e1", "edit_file", {"path": "calc.py"}, "Edited")
        record(self.ledger, "d1", "delete_file", {"path": "old.py"}, "Deleted")
        record(self.ledger, "c1", "run_command", {"command": "pytest -q"}, "Exit code: 1\nfailed")
        record(self.ledger, "c2", "run_command", {"command": "pytest -q -x"}, "Exit code: 0\nok")
        footer = task_footer(self.ledger.records)
        self.assertIn(COMMANDS_RAN, footer)
        self.assertIn("`pytest -q` -> exit 1", footer)
        self.assertIn("`pytest -q -x` -> exit 0", footer)
        self.assertIn("Files changed: calc.py, old.py", footer)
        self.assertNotIn(NO_COMMAND_RAN, footer)


if __name__ == "__main__":
    unittest.main()
