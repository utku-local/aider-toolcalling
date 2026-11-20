"""Drops a trailing `; echo "exit: $?"` or `|| true` from a command, because run_command reports the exit code.
Measured on Heretic and the 27B (expert eval, 2026-11-19): the exit-status echo was the most common reason a
verification command was declined in unattended runs, since `$` makes the whole command compound.
Removing the tail also keeps the real exit code: with the echo or `|| true` in place the command always exits 0.
"""

import re

EXIT_STATUS = "$?"
# One echo argument that expands nothing except `$?`: double-quoted, single-quoted or a bare word.
ECHO_ARGUMENT = r"""(?:"(?:[^"$`\\]|\$\?)*"|'[^']*'|(?:[\w:=.,-]|\$\?)+)"""
STATUS_ECHO_TAIL = re.compile(r"\s*(?:;|&&|\|\|)\s*echo(?:\s+" + ECHO_ARGUMENT + r")+\s*$")
IGNORE_FAILURE_TAIL = re.compile(r"\s*\|\|\s*true\s*$")


def without_one_tail(command: str) -> str:
    ignored = IGNORE_FAILURE_TAIL.search(command)
    if ignored:
        return command[: ignored.start()]
    echoed = STATUS_ECHO_TAIL.search(command)
    if echoed and EXIT_STATUS in echoed.group(0):
        return command[: echoed.start()]
    return command


def without_status_tail(command: str) -> str:
    """`command` without trailing exit-status echoes and `|| true`; unchanged when nothing would be left."""
    current = command.rstrip()
    while True:
        shorter = without_one_tail(current)
        if shorter == current:
            break
        current = shorter
    return current if current.strip() else command
