"""Adapters between the agent's user-facing tools and Aider's io: plan approval, plan notes and ask_user replies.
They decide when a user can answer at all: --yes-always runs are unattended, so plans are approved and questions
get no reply, which tells the model to decide itself.
Choices are printed numbered before the prompt, so the user can answer with a number.
"""

from typing import Any, Optional

PLAN_TITLE = "Approve this plan?"
NO_REPLY = ""


def unattended(coder: Any) -> bool:
    return coder.io.yes is True


def confirm_plan(coder: Any, plan: str) -> bool:
    """Show the plan and ask; an unattended run approves it."""
    if unattended(coder):
        return True
    return coder.io.confirm_ask(PLAN_TITLE, subject=plan, allow_never=False)


def ask_text(coder: Any, question: str) -> Optional[str]:
    """A free-text reply, or None when no one can answer."""
    if unattended(coder):
        return None
    reply = coder.io.prompt_ask(question, default=NO_REPLY)
    return reply.strip() or None


def answer_question(coder: Any, question: str, choices: list[str]) -> Optional[str]:
    """Print numbered choices, then read the reply; None when no one can answer."""
    if unattended(coder):
        return None
    for number, choice in enumerate(choices, start=1):
        coder.io.tool_output(f"  {number}. {choice}")
    return ask_text(coder, question)
