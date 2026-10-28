"""Applies a sampling seed to a model's request parameters, for --seed.
Some local servers fall back to a fixed default seed when a request has none, so every run with the same prompt
samples the same reply; passing a different seed per run makes repeated evaluations independent.
The seed is added to the model's extra_params, which Model.send_completion merges into every request.
"""

from typing import Any, Optional

SEED_PARAM = "seed"


def with_seed(extra_params: Optional[dict[str, Any]], seed: Optional[int]) -> Optional[dict[str, Any]]:
    """Copy of `extra_params` with `seed` set; unchanged when `seed` is None."""
    if seed is None:
        return extra_params
    return {**(extra_params or {}), SEED_PARAM: seed}
