"""Assembles streamed tool-call deltas into complete tool calls.
OpenAI-compatible servers send each tool call in fragments keyed by `index`: the id and name usually arrive once
and the JSON arguments arrive as string pieces that must be concatenated in order.
The assembled message has the same dict shape as a non-streamed one, so the normal tool loop can process it.
"""

from dataclasses import dataclass
from typing import Any

from aider.native_tool_calls import arguments_text, field


@dataclass
class PartialCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


class ToolCallAccumulator:
    """Collects tool-call deltas from stream chunks until the stream ends."""

    def __init__(self) -> None:
        self.calls: dict[int, PartialCall] = {}

    def add(self, delta: Any) -> bool:
        """Merge the tool-call fragments of one chunk delta; True when it carried any."""
        fragments = field(delta, "tool_calls") or []
        for position, fragment in enumerate(fragments):
            index = field(fragment, "index")
            call = self.calls.setdefault(position if index is None else index, PartialCall())
            call.id = call.id or field(fragment, "id") or ""
            function = field(fragment, "function") or {}
            call.name = call.name or field(function, "name") or ""
            arguments = field(function, "arguments")
            if arguments:
                call.arguments += arguments if isinstance(arguments, str) else arguments_text(arguments)
        return bool(fragments)

    def message(self, content: str) -> dict[str, Any]:
        """The streamed reply as a non-streamed message dict: text content plus complete tool calls."""
        return {
            "content": content,
            "tool_calls": [
                {"id": call.id, "function": {"name": call.name, "arguments": call.arguments}}
                for _, call in sorted(self.calls.items())
            ],
        }
