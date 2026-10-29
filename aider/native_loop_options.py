"""Optional behaviour of the tool loop, bundled so the loop's signature stays stable as features are added.
has_plan enables the plan-first check, spill saves long results to files, and hooks runs the project's hooks.
Every field defaults to None, which turns that behaviour off; the read-only research loop uses no options.
"""

from dataclasses import dataclass
from typing import Callable, Optional

from aider.native_hooks import ToolHooks
from aider.native_output_spill import OutputSpill


@dataclass(frozen=True)
class LoopOptions:
    has_plan: Optional[Callable[[], bool]] = None
    spill: Optional[OutputSpill] = None
    hooks: Optional[ToolHooks] = None


NO_OPTIONS = LoopOptions()
