"""The ask_user tool: the agent asks the user one question, optionally with choices, and continues with the answer.
Choices are numbered for the user, and a reply that is a number or an exact choice maps back to that choice.
When no one can answer (an unattended run with --yes-always), the model is told to decide and state its assumption.
"""

from typing import Callable, Optional

from aider.native_toolcalling import NativeToolError, NativeToolRegistry

# answer(question, choices) -> the user's reply, or None when no one can answer.
Answer = Callable[[str, list[str]], Optional[str]]
MAX_CHOICES = 6
NO_USER = (
    "No user is available to answer. Decide yourself, choose the most reasonable option, and say in your answer "
    "what you assumed."
)
ASK_PARAMETERS = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "description": "One clear question for the user."},
        "options": {
            "type": "array",
            "description": f"Up to {MAX_CHOICES} short choices; omit for a free-text answer.",
        },
    },
    "required": ["question"],
}


class AskError(NativeToolError):
    """Raised when ask_user gets an empty question or malformed choices."""


def resolve_choice(reply: str, choices: list[str]) -> str:
    """The choice a reply names by number or exact text; the reply itself otherwise."""
    text = reply.strip()
    if text.isdigit() and 1 <= int(text) <= len(choices):
        return choices[int(text) - 1]
    matching = [c for c in choices if c.lower() == text.lower()]
    return matching[0] if matching else text


def ask_user(answer: Answer, question: str, options: Optional[list] = None) -> str:
    choices = list(options or [])
    if not question.strip():
        raise AskError("question must not be empty")
    if len(choices) > MAX_CHOICES or not all(isinstance(c, str) and c.strip() for c in choices):
        raise AskError(f"options must be at most {MAX_CHOICES} non-empty strings")
    reply = answer(question.strip(), choices)
    if reply is None:
        return NO_USER
    return f"The user answered: {resolve_choice(reply, choices)}"


def register_ask_tool(registry: NativeToolRegistry, answer: Answer) -> None:
    registry.register(
        "ask_user",
        "Ask the user one question when you need a decision only they can make (a missing requirement, a choice "
        "between approaches). Prefer acting when the task is clear.",
        ASK_PARAMETERS,
        lambda question, options=None: ask_user(answer, question, options),
    )
