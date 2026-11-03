"""Saves and restores an agent session: chat history with tool messages, the operation ledger and the task list.
Agent mode saves after every request to .aider.agent-session.json in the project root (written atomically), and
--resume loads it into a new coder, so a session survives a restart with its real operation state.
Aider's own chat history file keeps only text, which is why tool calls and the ledger are stored separately here.
A new session that did not resume moves the saved one to .aider.agent-session.previous.json on its first save.
"""

import json
import os
from pathlib import Path
from typing import Any

from aider.native_tool_ledger import OperationRecord, OperationStatus

SESSION_FILE_NAME = ".aider.agent-session.json"
PREVIOUS_FILE_NAME = ".aider.agent-session.previous.json"
SESSION_VERSION = 1
SESSION_ENCODING = "utf-8"
TEMP_SUFFIX = ".tmp"
# Set on the coder once it owns the session file (it resumed it or saved it); until then a save keeps the old one.
OWNED_ATTRIBUTE = "native_session_owned"
OWNED_DEFAULT = False
KEPT_PREVIOUS = (
    "Started a new agent session; the previous one was kept as {name}. "
    "To resume it later, rename it to {current} and start with --resume."
)


class SessionError(ValueError):
    """Raised when a session file is missing, unreadable or from another version."""


def session_path(coder: Any) -> Path:
    return Path(coder.root) / SESSION_FILE_NAME


def session_data(coder: Any) -> dict[str, Any]:
    return {
        "version": SESSION_VERSION,
        "messages": list(coder.done_messages) + list(coder.cur_messages),
        "request": coder.native_ledger.request,
        "ledger": [
            {"call_id": r.call_id, "tool": r.tool, "arguments": r.arguments, "request": r.request,
             "status": r.status.value, "result": r.result}
            for r in coder.native_ledger.records
        ],
        "todos": [{"content": item.content, "status": item.status.value} for item in coder.native_todos.items],
    }


def keep_previous(coder: Any, path: Path) -> None:
    """Move another session's file aside before this session's first save, so a fresh start cannot erase it."""
    if getattr(coder, OWNED_ATTRIBUTE, OWNED_DEFAULT) or not path.exists():
        return
    os.replace(path, path.with_name(PREVIOUS_FILE_NAME))
    coder.io.tool_warning(KEPT_PREVIOUS.format(name=PREVIOUS_FILE_NAME, current=SESSION_FILE_NAME))


def save_session(coder: Any) -> None:
    path = session_path(coder)
    temp = path.with_name(path.name + TEMP_SUFFIX)
    try:
        keep_previous(coder, path)
        temp.write_text(json.dumps(session_data(coder), ensure_ascii=False), encoding=SESSION_ENCODING)
        os.replace(temp, path)
        setattr(coder, OWNED_ATTRIBUTE, True)
    except (OSError, TypeError, ValueError) as err:
        coder.io.tool_warning(f"Could not save the agent session: {err}")


def restore(coder: Any, data: dict[str, Any]) -> None:
    if not isinstance(data, dict) or data.get("version") != SESSION_VERSION:
        raise SessionError("unsupported session file version")
    coder.done_messages = list(data["messages"])
    coder.cur_messages = []
    coder.native_ledger.records = [
        OperationRecord(r["call_id"], r["tool"], r["arguments"], r["request"], OperationStatus(r["status"]),
                        r["result"])
        for r in data["ledger"]
    ]
    coder.native_ledger.request = int(data["request"])
    coder.native_todos.replace(data["todos"])


def resume_session(coder: Any) -> bool:
    """Load the saved session into `coder`; reports the outcome and returns whether it worked."""
    if getattr(coder, "native_ledger", None) is None:
        coder.io.tool_error("--resume needs agent mode or --native-tools.")
        return False
    try:
        restore(coder, json.loads(session_path(coder).read_text(encoding=SESSION_ENCODING)))
    except (OSError, ValueError, KeyError, TypeError) as err:
        coder.io.tool_error(f"Could not resume the agent session: {err}")
        return False
    setattr(coder, OWNED_ATTRIBUTE, True)
    coder.io.tool_output(
        f"Resumed agent session: {len(coder.done_messages)} messages, {len(coder.native_ledger.records)} operations."
    )
    return True
