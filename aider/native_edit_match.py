"""Finds where an edit_file old_string sits in a file, exactly or ignoring trailing whitespace on each line.
Local models often copy a block correctly but drop or add spaces at line ends, which made exact matching fail
repeatedly; a unique match that differs only there is safe to apply. When nothing matches, mismatch_hint names
the first line that differs, so the model can fix its old_string in one step instead of searching the file again.
"""

from typing import Optional

Span = tuple[int, int]
LINE_END_SPACE = " \t"


def exact_spans(text: str, old: str) -> list[Span]:
    spans: list[Span] = []
    start = text.find(old)
    while start != -1:
        spans.append((start, start + len(old)))
        start = text.find(old, start + len(old))
    return spans


def line_offsets(lines: list[str]) -> list[int]:
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    return offsets


def loose_spans(text: str, old: str) -> list[Span]:
    """Spans of whole-line blocks that equal `old` once trailing spaces and tabs are ignored on every line."""
    wanted = [line.rstrip(LINE_END_SPACE) for line in old.splitlines()]
    if not wanted:
        return []
    lines = text.splitlines(keepends=True)
    offsets = line_offsets(lines)
    keep_last_newline = old.endswith("\n")
    spans: list[Span] = []
    index = 0
    while index + len(wanted) <= len(lines):
        block = lines[index : index + len(wanted)]
        if [line.rstrip("\r\n").rstrip(LINE_END_SPACE) for line in block] == wanted:
            end = offsets[index + len(wanted)]
            if not keep_last_newline:
                end -= len(block[-1]) - len(block[-1].rstrip("\r\n"))
            spans.append((offsets[index], end))
            index += len(wanted)
        else:
            index += 1
    return spans


def find_spans(text: str, old: str) -> list[Span]:
    """Exact occurrences of `old`; when there are none, the occurrences that differ only in line-end whitespace."""
    return exact_spans(text, old) or loose_spans(text, old)


def replace_spans(text: str, spans: list[Span], new: str) -> str:
    parts: list[str] = []
    cursor = 0
    for start, end in spans:
        parts.append(text[cursor:start])
        parts.append(new)
        cursor = end
    parts.append(text[cursor:])
    return "".join(parts)


def mismatch_hint(text: str, old: str) -> Optional[str]:
    """Where the closest match of `old` stops matching, or None when its first line is not in the file."""
    wanted = [line.strip() for line in old.splitlines()]
    lines = text.splitlines()
    if not wanted:
        return None
    starts = [i for i, line in enumerate(lines) if line.strip() == wanted[0]]
    if not starts:
        return None
    best_start, best_length = starts[0], 0
    for start in starts:
        length = 0
        while length < len(wanted) and start + length < len(lines) and lines[start + length].strip() == wanted[length]:
            length += 1
        if length > best_length:
            best_start, best_length = start, length
    if best_length == len(wanted):
        return f"it matches lines {best_start + 1}-{best_start + best_length} only when indentation is ignored"
    line_number = best_start + best_length + 1
    actual = lines[line_number - 1] if line_number <= len(lines) else "(end of file)"
    return f"line {line_number} of the file is {actual!r}, but old_string has {old.splitlines()[best_length]!r}"
