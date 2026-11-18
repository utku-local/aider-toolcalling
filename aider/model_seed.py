"""Applies a sampling seed to a model's request parameters, for --seed.
Some local servers fall back to a fixed default seed when a request has none, so every run with the same prompt
samples the same reply; passing a different seed per run makes repeated evaluations independent.
The seed is added to the model's extra_params, which Model.send_completion merges into every request.
Because that one seed is sent with every request of a session, a model that falls into a loop samples the same
reply to nearly the same prompt each time; next_seed moves to another seed when the tool loop detects a repeat.
"""

from typing import Any, Optional

SEED_PARAM = "seed"
# The seed a request without one is taken to have, so the first step away from it is a real change.
UNSET_SEED = 0
SEED_STEP = 1


def with_seed(extra_params: Optional[dict[str, Any]], seed: Optional[int]) -> Optional[dict[str, Any]]:
    """Copy of `extra_params` with `seed` set; unchanged when `seed` is None."""
    if seed is None:
        return extra_params
    return {**(extra_params or {}), SEED_PARAM: seed}


def next_seed(extra_params: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Copy of `extra_params` with the seed moved one step on; a run with the same --seed still repeats exactly.

    Measured on the 27B (expert eval, expr-eval and scheduler): refused a repeated command and sent back for a
    promise, it returned the same sentence and the same command call four times in a row."""
    params = dict(extra_params or {})
    current = params.get(SEED_PARAM)
    params[SEED_PARAM] = (current if isinstance(current, int) else UNSET_SEED) + SEED_STEP
    return params
