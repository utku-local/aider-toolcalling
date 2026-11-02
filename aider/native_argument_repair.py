"""Repairs two malformed tool-argument shapes whose meaning is unambiguous, before the arguments are validated.
A key with stray quotes or spaces (`items"`) is renamed to the declared parameter it names, and an array or object
parameter sent as a JSON string is decoded. Measured: Heretic sent todo_write `{"items\"": "[...]"}` twice in one run.
Anything else is left as it is, so validation still reports it to the model.
"""

import json
from typing import Any

STRAY_KEY_CHARS = "\"' \t\n"
STRUCTURED_TYPES = {"array": list, "object": dict}


def repaired_key(name: str, properties: dict[str, Any], arguments: dict[str, Any]) -> str:
    """The declared parameter `name` means once stray quotes and spaces are stripped; `name` when there is none."""
    if name in properties:
        return name
    clean = name.strip(STRAY_KEY_CHARS)
    if clean != name and clean in properties and clean not in arguments:
        return clean
    return name


def decoded_value(value: Any, spec: dict[str, Any]) -> Any:
    """`value` decoded from a JSON string when the parameter is an array or object and it decodes to that type."""
    expected = STRUCTURED_TYPES.get(spec.get("type"))
    if expected is None or not isinstance(value, str):
        return value
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return value
    return decoded if isinstance(decoded, expected) else value


def repair_arguments(parameters: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Copy of `arguments` with stray-quoted keys renamed and stringified arrays or objects decoded."""
    properties = parameters.get("properties") or {}
    repaired: dict[str, Any] = {}
    for name, value in arguments.items():
        key = repaired_key(name, properties, arguments)
        if key in repaired:
            key = name
        repaired[key] = decoded_value(value, properties.get(key) or {})
    return repaired
