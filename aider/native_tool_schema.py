"""Validates decoded tool arguments against the JSON schema a tool was registered with.
It checks required properties, rejects unknown ones and verifies the basic JSON types of each value.
The returned messages are written for the model, so it can correct its next call.
"""

from typing import Any

JSON_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "null": (type(None),),
}
NUMERIC_TYPES = ("integer", "number")


def type_matches(value: Any, expected: str) -> bool:
    allowed = JSON_TYPES.get(expected)
    if allowed is None:
        return True
    if expected in NUMERIC_TYPES and isinstance(value, bool):
        return False
    return isinstance(value, allowed)


def validate_arguments(parameters: dict[str, Any], arguments: dict[str, Any]) -> list[str]:
    """Problems with `arguments` under the `parameters` object schema; empty when valid."""
    properties = parameters.get("properties") or {}
    problems = [
        f"missing required argument {name!r}"
        for name in parameters.get("required") or []
        if name not in arguments
    ]
    for name, value in arguments.items():
        spec = properties.get(name)
        if spec is None:
            problems.append(f"unknown argument {name!r}; expected one of {sorted(properties)}")
            continue
        expected = spec.get("type")
        if isinstance(expected, str) and not type_matches(value, expected):
            problems.append(f"argument {name!r} must be of type {expected}")
    return problems
