"""The agent's task list: a todo_write tool that replaces the list, and its rendering for the working state.
The model plans multi-step work as items with a status (pending, in_progress, done) and updates them as it goes;
the open items are shown with every request so steps are not forgotten after old results are compacted.
Items are validated here because the shared schema check only verifies top-level argument types; the first
plan of each request can be shown to the user for approval, and a rejected plan is cleared with the user's note.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Optional

from aider.native_toolcalling import NativeToolError, NativeToolRegistry


class TodoStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"


@dataclass(frozen=True)
class TodoItem:
    content: str
    status: TodoStatus


MAX_TODO_ITEMS = 30
# confirm(plan) -> True to approve; note(question) -> the user's text, or None when no one can answer.
ConfirmPlan = Callable[[str], bool]
AskNote = Callable[[str], Optional[str]]
PLAN_APPROVED = "The user approved this plan. Work through it.\n"
PLAN_REJECTED = (
    "The user did not approve the plan; it was cleared. Their note: {note}\n"
    "Write a revised plan with todo_write before changing files."
)
NO_NOTE = "(no note given)"
PLAN_CHANGE_QUESTION = "What should change in the plan?"
STATUS_MARKS = {TodoStatus.PENDING: "[ ]", TodoStatus.IN_PROGRESS: "[~]", TodoStatus.DONE: "[x]"}
TODO_PARAMETERS = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": 'The whole list, replacing the last: [{"content", "status": "pending" | "in_progress" | '
            '"done"}].',
        },
    },
    "required": ["items"],
}


class TodoError(NativeToolError):
    """Raised when todo_write receives a malformed item list."""


class TodoList:
    """The current task list of a session."""

    def __init__(self) -> None:
        self.items: tuple[TodoItem, ...] = ()
        # Reset at the start of every request, so each request's first plan is shown for approval.
        self.approved = False

    def replace(self, raw_items: list[Any]) -> None:
        if len(raw_items) > MAX_TODO_ITEMS:
            raise TodoError(f"At most {MAX_TODO_ITEMS} items")
        self.items = tuple(parse_item(raw) for raw in raw_items)

    def render(self) -> str:
        return "\n".join(f"{STATUS_MARKS[item.status]} {item.content}" for item in self.items)

    def open_items(self) -> tuple[TodoItem, ...]:
        return tuple(item for item in self.items if item.status is not TodoStatus.DONE)


def parse_item(raw: Any) -> TodoItem:
    if not isinstance(raw, dict) or not isinstance(raw.get("content"), str) or not raw["content"].strip():
        raise TodoError('Each item needs a non-empty "content" string')
    try:
        status = TodoStatus(raw.get("status", TodoStatus.PENDING.value))
    except ValueError as err:
        raise TodoError(f"Unknown status {raw.get('status')!r}; use pending, in_progress or done") from err
    return TodoItem(raw["content"].strip(), status)


def todo_write(
    todos: TodoList, items: list[Any], confirm: Optional[ConfirmPlan] = None, note: Optional[AskNote] = None
) -> str:
    """Replace the list; with `confirm`, the request's first non-empty plan needs the user's approval."""
    todos.replace(items)
    rendered = todos.render()
    if not rendered:
        return "Task list cleared."
    if confirm is None or todos.approved:
        return rendered
    if confirm(rendered):
        todos.approved = True
        return PLAN_APPROVED + rendered
    reason = note(PLAN_CHANGE_QUESTION) if note else None
    todos.replace([])
    return PLAN_REJECTED.format(note=reason or NO_NOTE)


def register_todo_tool(
    registry: NativeToolRegistry, todos: TodoList, confirm: Optional[ConfirmPlan] = None,
    note: Optional[AskNote] = None,
) -> None:
    """Add todo_write, bound to `todos`; `confirm` None means plans are never shown for approval."""
    registry.register(
        "todo_write",
        "Write and update your task list for multi-step work, with one item in_progress at a time.",
        TODO_PARAMETERS,
        lambda items: todo_write(todos, items, confirm, note),
    )
