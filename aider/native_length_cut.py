"""Handles a model reply that was cut off at the output limit while the agent is working with tools.
Upstream Aider ends the request there ("has hit a token limit"); for an agent that is one bad reply, not the end.
Measured on Heretic (expert eval, scheduler): after two file reads it reasoned in prose, "Actually wait" after
"Hmm, let me think again", for 14,816 tokens with no tool call, and the task ended without a single edit.
The cut reply is shortened so it is not re-read on every later round, and the model is sent back to act.
"""

KEPT_CHARS = 1500
CUT_MARKER = "\n[The rest of this reply was cut off: it reached the output limit.]"
MAX_LENGTH_CUT_NUDGES = 2
LENGTH_CUT_WARNING = "The model's reply reached the output limit; sending it back to act instead of ending."
LENGTH_CUT_NUDGE = (
    "Your last reply reached the output limit and was cut off before it did anything. Do not continue the analysis "
    "in prose and do not repeat it. Make one tool call now: run the tests or a short command that shows the actual "
    "behaviour, or make one edit. Keep every reply short; think by running things, not by writing."
)


def shorten_cut_reply(text: str) -> str:
    """The start of a cut-off reply plus a marker; a reply that is already short is only marked."""
    return text[:KEPT_CHARS].rstrip() + CUT_MARKER


def may_nudge_length_cut(nudges_used: int) -> bool:
    """Whether a cut-off reply may still be sent back in this request."""
    return nudges_used < MAX_LENGTH_CUT_NUDGES
