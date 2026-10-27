"""Normalizes tool calls from any OpenAI-compatible response shape into ToolCall records.
It accepts structured tool_calls given as objects or dicts, with arguments as a JSON string or a dict, and
falls back to <tool_call>{...}</tool_call> blocks written into the message text, as Qwen-style templates emit.
Calls without an id get a deterministic synthetic id so the assistant and tool messages always agree.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Optional

TEXT_TOOL_CALL = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)
SYNTHETIC_ID_FORMAT = "call_{round}_{index}"
EMPTY_ARGUMENTS = "{}"
UNKNOWN_TOOL_NAME = "unknown"


@dataclass(frozen=True)
class ToolCall:
    """One requested call; `arguments` is always the raw JSON text sent back to the model."""

    id: str
    name: str
    arguments: str


def field(item: Any, key: str) -> Any:
    """Read `key` from a dict or an attribute-style object; None when absent."""
    if isinstance(item, dict):
        return item.get(key)
    return getattr(item, key, None)


def arguments_text(raw: Any) -> str:
    if raw is None or raw == "":
        return EMPTY_ARGUMENTS
    if isinstance(raw, str):
        return raw
    return json.dumps(raw, ensure_ascii=False)


def structured_calls(message: Any) -> list[Any]:
    return list(field(message, "tool_calls") or [])


def text_calls(content: Optional[str]) -> list[dict[str, Any]]:
    """Parse <tool_call> blocks; blocks that are not a JSON object with a name are ignored."""
    found = []
    for block in TEXT_TOOL_CALL.findall(content or ""):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and isinstance(data.get("name"), str):
            found.append({"function": {"name": data["name"], "arguments": data.get("arguments")}})
    return found


def strip_text_calls(content: Optional[str]) -> str:
    return TEXT_TOOL_CALL.sub("", content or "").strip()


def normalize_tool_calls(message: Any, round_index: int) -> list[ToolCall]:
    """Every tool call on `message`, structured ones first, else ones written in the text."""
    raw_calls = structured_calls(message) or text_calls(field(message, "content"))
    calls = []
    for index, raw in enumerate(raw_calls):
        function = field(raw, "function") or {}
        calls.append(
            ToolCall(
                id=field(raw, "id") or SYNTHETIC_ID_FORMAT.format(round=round_index, index=index),
                name=field(function, "name") or UNKNOWN_TOOL_NAME,
                arguments=arguments_text(field(function, "arguments")),
            )
        )
    return calls


def visible_content(message: Any) -> str:
    """Message text with any <tool_call> blocks removed."""
    return strip_text_calls(field(message, "content"))
