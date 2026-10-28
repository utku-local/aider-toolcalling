"""Pure helpers for syncing this package's dependencies with an upstream aider-chat release.
They read the runtime requirements from a wheel's METADATA (skipping extras) and rewrite the dependencies array of
pyproject.toml with them, quoting each entry so environment markers with double quotes stay valid TOML.
Nothing here touches the network or the filesystem.
"""

import json
import re

REQUIRES_PREFIX = "Requires-Dist: "
EXTRA_MARKER = "extra =="
DEPENDENCIES_BLOCK = re.compile(r"^dependencies = \[\n.*?^\]\n", re.MULTILINE | re.DOTALL)
INDENT = "    "


class PyprojectError(ValueError):
    """Raised when pyproject.toml has no dependencies array to replace."""


def runtime_requirements(metadata: str) -> list[str]:
    """Requires-Dist entries of a wheel's METADATA that are not tied to an extra."""
    return [
        line[len(REQUIRES_PREFIX):].strip()
        for line in metadata.splitlines()
        if line.startswith(REQUIRES_PREFIX) and EXTRA_MARKER not in line
    ]


def replace_dependencies(pyproject: str, requirements: list[str]) -> str:
    """pyproject.toml text with its dependencies array replaced by `requirements`."""
    if not DEPENDENCIES_BLOCK.search(pyproject):
        raise PyprojectError("pyproject.toml has no 'dependencies = [' block")
    block = "dependencies = [\n" + "".join(f"{INDENT}{json.dumps(r)},\n" for r in requirements) + "]\n"
    return DEPENDENCIES_BLOCK.sub(lambda _: block, pyproject, count=1)
