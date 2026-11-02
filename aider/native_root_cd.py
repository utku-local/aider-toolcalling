"""Drops a leading `cd <project root> &&` (or `;`) from a command, because agent commands already run in the root.
Measured: Heretic prefixed every command with `cd /abs/project/path &&` although the system prompt names the
working directory, which made each command compound and raised an approval risk for nothing.
Only a cd whose target resolves to the root is dropped; any other cd changes behaviour and is kept.
"""

import re
import shlex
from pathlib import Path

# `cd <target> && rest` or `cd <target>; rest`; the target may be quoted.
ROOT_CD = re.compile(r"""^\s*cd\s+(?P<target>'[^']*'|"[^"]*"|[^\s;&|]+)\s*(?:&&|;)\s*(?P<rest>\S.*)$""", re.DOTALL)


def resolves_to_root(target: str, root: Path) -> bool:
    """True when the cd target, absolute or relative to `root`, is `root` itself."""
    try:
        words = shlex.split(target)
    except ValueError:
        return False
    if len(words) != 1:
        return False
    path = Path(words[0]).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve() == root.resolve()


def without_root_cd(command: str, root: Path) -> str:
    """`command` without a leading cd into `root`; unchanged when there is none or it goes elsewhere."""
    match = ROOT_CD.match(command)
    if not match or not resolves_to_root(match.group("target"), root):
        return command
    return match.group("rest")
