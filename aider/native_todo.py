"""The agent's task list: a todo_write tool that replaces the list, and its rendering for the working state.
The model plans multi-step work as items with a status (pending, in_progress, done) and updates them as it goes;
the open items are shown with every request so steps are not forgotten after old results are compacted.
Items are validated here because the shared schema check only verifies top-level argument types.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

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
STATUS_MARKS = {TodoStatus.PENDING: "[ ]", TodoStatus.IN_PROGRESS: "[~]", TodoStatus.DONE: "[x]"}
TODO_PARAMETERS = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "description": "The complete task list, replacing the previous one. Each item is "
            '{"content": "<step>", "status": "pending" | "in_progress" | "done"}.',
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


def todo_write(todos: TodoList, items: list[Any]) -> str:
    todos.replace(items)
    return todos.render() or "Task list cleared."


def register_todo_tool(registry: NativeToolRegistry, todos: TodoList) -> None:
    """Add todo_write, bound to `todos`, to `registry`."""
    registry.register(
        "todo_write",
        "Write your task list for multi-step work and keep it updated: mark one item in_progress at a time "
        "and mark items done as you finish them.",
        TODO_PARAMETERS,
        lambda items: todo_write(todos, items),
    )
