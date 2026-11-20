"""Recognizes shell command shapes the command policy can judge part by part instead of calling them compound.
A newline inside quotes belongs to an argument (`python -c "two\nlines"`), a here-document with a literal body is
only the standard input of the command on its first line, and a list joined by &&, || or ; is a sequence of
separate commands, of which an `echo` of literal text between two others only prints a separator. Measured on the
27B: these shapes were most of the verification commands it wrote, and each was declined in unattended runs.
Everything here is pure text handling; nothing is executed.
"""

import re
from typing import Optional

SINGLE_QUOTE = "'"
DOUBLE_QUOTE = '"'
ESCAPE = "\\"
NEWLINE = "\n"
LIST_SEPARATORS = frozenset({"&&", "||", ";"})
OPERATOR_CHARS = frozenset("|&;<>()")
# Programs that only print their arguments; as a middle part of a list they change neither files nor the exit code.
PRINT_ONLY_PROGRAMS = frozenset({"echo"})
BODY_EXPANSION_CHARS = frozenset("$`")
# `<head> <<'WORD'`, the body, then WORD alone on the last line; the head must hold no other `<`.
HEREDOC = re.compile(
    r"^(?P<head>[^\n<]*?)\s*<<(?P<dash>-?)\s*(?P<quote>['\"]?)(?P<word>[A-Za-z_][A-Za-z0-9_]*)(?P=quote)[ \t]*\n"
    r"(?P<body>.*?)\n[ \t]*(?P=word)\s*$",
    re.DOTALL,
)


def has_unquoted_newline(command: str) -> bool:
    """True when a newline separates commands; a newline inside single or double quotes is argument text."""
    quote = ""
    escaped = False
    for char in command.strip():
        if escaped:
            escaped = False
        elif char == ESCAPE and quote != SINGLE_QUOTE:
            escaped = True
        elif quote:
            quote = "" if char == quote else quote
        elif char in (SINGLE_QUOTE, DOUBLE_QUOTE):
            quote = char
        elif char == NEWLINE:
            return True
    return False


def without_heredoc(command: str) -> Optional[str]:
    """The first line of `command` without its here-document, or None when it has none the policy can trust.

    Trusted means: nothing follows the delimiter word on the first line or after the closing line, the body
    cannot end early (no body line equals the word), and the body is literal: a quoted word, or no `$` and no
    backtick in the body, so the shell expands nothing in it.
    """
    match = HEREDOC.match(command.strip())
    if not match:
        return None
    word, body = match.group("word"), match.group("body")
    if any(line.strip() == word for line in body.split(NEWLINE)):
        return None
    if not match.group("quote") and BODY_EXPANSION_CHARS & set(body):
        return None
    return match.group("head").strip() or None


def list_segments(tokens: list[str]) -> list[list[str]]:
    """The commands of a list joined by &&, || or ;, as token lists; one segment when there is no separator.

    An empty segment (a leading, trailing or doubled separator) is kept, so the caller can refuse the list.
    """
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in LIST_SEPARATORS:
            segments.append([])
        else:
            segments[-1].append(token)
    return segments


def prints_only(segment: list[str]) -> bool:
    """True for `echo` with plain arguments: no pipe, redirect or other operator among its tokens."""
    return bool(segment) and segment[0] in PRINT_ONLY_PROGRAMS and not any(
        token and set(token) <= OPERATOR_CHARS for token in segment
    )


def without_separator_echoes(segments: list[list[str]]) -> list[list[str]]:
    """`segments` without print-only parts, except the last one: the last command decides the exit code, so an
    echo there would report success whatever happened before it."""
    return [s for s in segments[:-1] if not prints_only(s)] + segments[-1:]
