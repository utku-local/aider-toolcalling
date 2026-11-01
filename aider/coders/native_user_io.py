"""Adapters between the agent and Aider's io: plan approval, plan notes, ask_user replies and user notes.
They decide when a user can answer at all: --yes-always runs are unattended, so plans are approved and questions
get no reply, which tells the model to decide itself.
Choices are printed numbered before the prompt, so the user can answer with a number. Messages the user types at a
confirmation prompt, or after declining a command, are queued on io and handed to the model as a user message.
"""

from typing import Any, Optional

PLAN_TITLE = "Approve this plan?"
NO_REPLY = ""
DECLINE_FOLLOW_UP = "Declined. What should the agent do instead? (Enter to let it decide)"
USER_NOTE_HEADING = "Message from the user, typed while you were working (it overrides your current plan):\n"


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


def ask_after_decline(coder: Any) -> None:
    """After a declined action, let the user say what to do instead; the reply is queued for the model.
    Measured: told by the tool result to ask the user, a local model tried another approach instead."""
    if coder.io.yes is not None:
        return
    reply = coder.io.prompt_ask(DECLINE_FOLLOW_UP, default=NO_REPLY).strip()
    if reply:
        coder.io.pending_user_notes.append(reply)


def take_user_notes(coder: Any) -> Optional[dict[str, str]]:
    """The queued user notes as one user message, clearing the queue; None when there are none."""
    notes = getattr(coder.io, "pending_user_notes", None)
    if not notes:
        return None
    content = USER_NOTE_HEADING + "\n".join(notes)
    notes.clear()
    return {"role": "user", "content": content}
