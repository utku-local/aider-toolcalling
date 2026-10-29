"""Validates decoded tool arguments against the JSON schema a tool was registered with.
It checks required properties, rejects unknown ones and verifies the basic JSON types of each value; the returned
messages are written for the model, so it can correct its next call.
Integer parameters are sent to the model as numbers and whole numbers like 120.0 are turned back into integers,
because some servers' tool parsers (mlx_lm's qwen3_coder) drop a whole call when an "integer" value reads 120.0.
"""

import copy
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
INTEGER_TYPE = "integer"
WIRE_INTEGER_TYPE = "number"
WHOLE_NUMBER_NOTE = " (a whole number)"


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


def wire_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Copy of `parameters` as sent to the model: integer properties become numbers described as whole numbers."""
    wire = copy.deepcopy(parameters)
    for spec in (wire.get("properties") or {}).values():
        if spec.get("type") == INTEGER_TYPE:
            spec["type"] = WIRE_INTEGER_TYPE
            spec["description"] = spec.get("description", "") + WHOLE_NUMBER_NOTE
    return wire


def coerce_integers(parameters: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Copy of `arguments` with whole-number floats (120.0) of integer properties turned into ints."""
    properties = parameters.get("properties") or {}
    return {
        name: int(value)
        if (properties.get(name) or {}).get("type") == INTEGER_TYPE and isinstance(value, float) and value.is_integer()
        else value
        for name, value in arguments.items()
    }
