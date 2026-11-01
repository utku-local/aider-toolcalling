"""Pure rules for reading a reply to a yes/no confirmation prompt.
Only the answers the prompt actually shows are accepted: a bare (Y)es/(N)o prompt takes yes or no, "all" and
"skip" exist only for grouped prompts, and "don't" only when the prompt offers it. Anything else is asked again,
except a reply of several words, which is a message for the model that the user typed at the wrong moment.
"""

from enum import Enum
from typing import Optional

YES = "yes"
NO = "no"
ALL = "all"
SKIP = "skip"
DONT = "don't"


class ReplyKind(str, Enum):
    ANSWER = "answer"
    NOTE = "note"
    INVALID = "invalid"


def offered_answers(grouped: bool, explicit_yes_required: bool, allow_never: bool) -> list[str]:
    """The answers a prompt shows, in display order; mirrors the "(Y)es/(N)o/..." text."""
    answers = [YES, NO]
    if grouped and not explicit_yes_required:
        answers.append(ALL)
    if grouped:
        answers.append(SKIP)
    if allow_never:
        answers.append(DONT)
    return answers


def classify_reply(reply: str, offered: list[str]) -> tuple[ReplyKind, Optional[str]]:
    """(ANSWER, the full answer) for a prefix of an offered answer, (NOTE, the text) for a reply of several words,
    (INVALID, None) otherwise. An empty reply is not handled here: it takes the prompt's default."""
    text = reply.strip()
    lowered = text.lower()
    matches = [answer for answer in offered if lowered and answer.startswith(lowered)]
    if matches:
        return ReplyKind.ANSWER, matches[0]
    if len(text.split()) > 1:
        return ReplyKind.NOTE, text
    return ReplyKind.INVALID, None
