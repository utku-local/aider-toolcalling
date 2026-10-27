"""Appends finished operations from the ledger to a JSON Lines audit log in the project root.
Each line records the call id, tool, arguments, request number, final status and result size, so what the agent
did can be reviewed after the session; full results stay out of the log to keep it small.
Logging failures are reported once as a warning and never stop the agent.
"""

import json
from pathlib import Path
from typing import Any

from aider.native_tool_ledger import OperationRecord

LOG_FILE_NAME = ".aider.tools.jsonl"
LOG_ENCODING = "utf-8"


def log_line(record: OperationRecord) -> str:
    return json.dumps(
        {
            "call_id": record.call_id,
            "tool": record.tool,
            "arguments": record.arguments,
            "request": record.request,
            "status": record.status.value,
            "result_chars": len(record.result),
        },
        ensure_ascii=False,
    )


def append_operation_log(coder: Any, records: list[OperationRecord]) -> None:
    if not records or coder.native_log_failed:
        return
    try:
        with open(Path(coder.root) / LOG_FILE_NAME, "a", encoding=LOG_ENCODING) as handle:
            for record in records:
                handle.write(log_line(record) + "\n")
    except OSError as err:
        coder.native_log_failed = True
        coder.io.tool_warning(f"Could not write the tool log: {err}")
