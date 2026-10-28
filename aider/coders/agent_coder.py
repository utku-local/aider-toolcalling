"""The agent chat mode: the model works through native tools, like a coding agent, instead of an edit format.
It enables the full tool set (read, search, edit, shell) and reports files changed by tools to Aider's normal
post-edit flow, so linting, auto-commits and tests behave as they do for any other edit.
Write approvals are grouped per request, so answering "All" approves the remaining edits of that request only.
"""

from typing import Any, Iterator

from aider.io import ConfirmGroup
from aider.native_toolcalling import NativeToolRegistry

from .agent_prompts import AgentPrompts
from .base_coder import Coder
from .native_agent_config import instruction_files
from .native_session import save_session
from .native_tool_setup import build_native_tools


AGENT_MAX_MAP_TOKENS = 1024
AGENT_MAP_MULTIPLIER = 1


class AgentCoder(Coder):
    """Explore, edit and verify the project through tools."""

    edit_format = "agent"
    gpt_prompts = AgentPrompts()

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        kwargs["native_tools"] = True
        # The agent finds files with its search tools, so a large repo map mostly costs prefill time on every
        # round: cap it and drop the "no files in chat" multiplier. --map-tokens 0 still turns it off.
        kwargs["map_tokens"] = min(kwargs.get("map_tokens", AGENT_MAX_MAP_TOKENS), AGENT_MAX_MAP_TOKENS)
        kwargs["map_mul_no_files"] = AGENT_MAP_MULTIPLIER
        super().__init__(*args, **kwargs)
        # Project instructions (AGENTS.md, CLAUDE.md) are always in view, like a coding agent's memory file.
        self.abs_read_only_fnames.update(instruction_files(self.root))

    def build_native_tools(self) -> NativeToolRegistry:
        return build_native_tools(self, include_actions=True)

    def send_message(self, inp: str) -> Iterator[str]:
        self.native_write_group = ConfirmGroup()
        self.native_ledger.start_request()
        yield from super().send_message(inp)
        save_session(self)

    def check_for_file_mentions(self, content: str) -> None:
        """The agent reads files through tools, so mentions never prompt to add files."""
        return None

    def apply_updates(self) -> set[str]:
        """Files changed by tools during this reply, relative to the root."""
        edited = {self.get_rel_fname(path) for path in self.native_pending_edits}
        self.native_pending_edits.clear()
        return edited
