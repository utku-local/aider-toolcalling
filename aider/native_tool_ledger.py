"""Operation ledger: the record of what each tool call actually did, kept apart from the chat history.
Every call gets an OperationRecord with its id, tool, arguments, request number, status and result, and the status
moves through explicit transitions (started, awaiting approval, approved or denied, executed or failed).
A call id that already finished in the current request is never executed again, so a replayed response is harmless.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class OperationStatus(str, Enum):
    STARTED = "started"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    DENIED = "denied"
    EXECUTED = "executed"
    FAILED = "failed"


FINAL_STATUSES = frozenset({OperationStatus.DENIED, OperationStatus.EXECUTED, OperationStatus.FAILED})
NO_RESULT = ""


@dataclass
class OperationRecord:
    """One tool call; `result` is the text returned to the model once the call is final."""

    call_id: str
    tool: str
    arguments: str
    request: int
    status: OperationStatus = OperationStatus.STARTED
    result: str = NO_RESULT

    @property
    def final(self) -> bool:
        return self.status in FINAL_STATUSES


class OperationLedger:
    """All operations of a session; `current` is the call being executed right now, if any."""

    def __init__(self) -> None:
        self.records: list[OperationRecord] = []
        self.request = 0
        self.current: Optional[OperationRecord] = None

    def start_request(self) -> None:
        self.request += 1

    def finished(self, call_id: str) -> Optional[OperationRecord]:
        """The final record of `call_id` in the current request, if it already ran."""
        for record in reversed(self.records):
            if record.request == self.request and record.call_id == call_id and record.final:
                return record
        return None

    def begin(self, call_id: str, tool: str, arguments: str) -> OperationRecord:
        record = OperationRecord(call_id, tool, arguments, self.request)
        self.records.append(record)
        self.current = record
        return record

    def mark(self, status: OperationStatus) -> None:
        """Record an approval step of the current call."""
        if self.current is not None and not self.current.final:
            self.current.status = status

    def finish(self, record: OperationRecord, result: str, failed: bool) -> None:
        """Close a call; a denied call stays denied whatever text the tool returned."""
        if record.status is not OperationStatus.DENIED:
            record.status = OperationStatus.FAILED if failed else OperationStatus.EXECUTED
        record.result = result
        if self.current is record:
            self.current = None

    def ran_before(self, record: OperationRecord) -> bool:
        """True when the same tool already ran with the same arguments earlier in this request."""
        return any(
            r is not record and r.request == record.request and r.tool == record.tool
            and r.arguments == record.arguments and r.status is OperationStatus.EXECUTED
            for r in self.records
        )

    def times_run(self, tool: str, arguments: str) -> int:
        """How often this exact call already executed in the current request."""
        return sum(
            1 for r in self.records
            if r.request == self.request and r.tool == tool and r.arguments == arguments
            and r.status is OperationStatus.EXECUTED
        )

    def repeat_refusals(self, marker: str) -> int:
        """Calls refused as repeats in the current request (their result starts with `marker`)."""
        return sum(1 for r in self.records if r.request == self.request and r.result.startswith(marker))

    def executed(self) -> list[OperationRecord]:
        return [r for r in self.records if r.status is OperationStatus.EXECUTED]
